import json
from datetime import UTC, datetime

import httpx
import pytest

from legalrag import llm

MONDAY = (2026, 10, 26)
SATURDAY = (2026, 10, 24)


def at(day, hour):
    return datetime(*day, hour, 0, tzinfo=UTC)


def reply(content="{}", hit=100, miss=900, completion=50, reasoning=None):
    usage = {
        "prompt_tokens": hit + miss,
        "prompt_cache_hit_tokens": hit,
        "prompt_cache_miss_tokens": miss,
        "completion_tokens": completion,
    }
    if reasoning is not None:
        usage["completion_tokens_details"] = {"reasoning_tokens": reasoning}
    return {"id": "req-1", "choices": [{"message": {"content": content}}], "usage": usage}


def fake_http(handler):
    return llm.make_http("key", httpx.MockTransport(handler))


def call(http, tmp_path, budget=None, **kwargs):
    return llm.chat(
        http,
        tmp_path / "ledger.jsonl",
        budget or llm.Budget(run_cap=1.0, total_cap=5.0),
        "test",
        "deepseek-flash",
        [{"role": "user", "content": "json please"}],
        max_tokens=500,
        **kwargs,
    )


def test_peak_hours_follow_the_price_page():
    assert llm.is_peak(at(MONDAY, 1)) and llm.is_peak(at(MONDAY, 3))
    assert not llm.is_peak(at(MONDAY, 4)) and not llm.is_peak(at(MONDAY, 5))
    assert llm.is_peak(at(MONDAY, 6)) and llm.is_peak(at(MONDAY, 9))
    assert not llm.is_peak(at(MONDAY, 10))
    assert not llm.is_peak(at(SATURDAY, 2))


def test_cost_uses_the_three_prices_and_halves_off_peak():
    peak = llm.cost_usd("deepseek-flash", 1_000_000, 1_000_000, 1_000_000, at(MONDAY, 2))
    assert peak == pytest.approx(0.006 + 0.30 + 1.20)
    assert llm.cost_usd("deepseek-flash", 1_000_000, 1_000_000, 1_000_000, at(SATURDAY, 2)) == (
        pytest.approx(peak / 2)
    )
    assert llm.cost_usd("deepseek-v4-pro", 0, 1_000_000, 0, at(MONDAY, 2)) == pytest.approx(1.32)


def test_worst_case_counts_every_input_token_as_a_miss_and_the_full_output():
    assert llm.worst_case_cost("deepseek-flash", 1000, 500) == pytest.approx(0.0009)
    assert llm.estimate_tokens("a" * 11) == 6


def test_budget_refuses_when_the_worst_case_does_not_fit():
    budget = llm.Budget(run_cap=1.0, total_cap=5.0, spent=0.9)
    with pytest.raises(llm.BudgetExceeded, match="run cap"):
        llm.ensure_within_budget(budget, 0.9, 0.2)
    with pytest.raises(llm.BudgetExceeded, match="total cap"):
        llm.ensure_within_budget(llm.Budget(1.0, 5.0), 4.9, 0.2)
    llm.ensure_within_budget(llm.Budget(1.0, 5.0), 0.0, 0.2)


def test_a_call_is_logged_with_its_cost_and_sent_without_thinking(tmp_path):
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=reply('{"q": 1}', reasoning=0))

    budget = llm.Budget(run_cap=1.0, total_cap=5.0)
    assert call(fake_http(handler), tmp_path, budget) == '{"q": 1}'

    assert sent[0]["thinking"] == {"type": "disabled"}
    assert sent[0]["response_format"] == {"type": "json_object"}
    assert sent[0]["max_tokens"] == 500
    [entry] = llm.read_ledger(tmp_path / "ledger.jsonl")
    assert entry["type"] == "call" and entry["prompt_tokens"] == 1000
    assert entry["cache_hit_tokens"] == 100 and entry["reasoning_tokens"] == 0
    assert entry["cost_usd"] > 0 and budget.spent == pytest.approx(entry["cost_usd"])
    assert llm.ledger_total(tmp_path / "ledger.jsonl") == pytest.approx(entry["cost_usd"])


def test_a_call_over_budget_is_never_sent(tmp_path):
    def handler(request):
        raise AssertionError("must not reach the network")

    with pytest.raises(llm.BudgetExceeded):
        call(fake_http(handler), tmp_path, llm.Budget(run_cap=0.0001, total_cap=5.0))


def test_the_ledger_total_counts_earlier_runs(tmp_path):
    llm.append_ledger(tmp_path / "ledger.jsonl", {"type": "call", "cost_usd": 4.9999})
    with pytest.raises(llm.BudgetExceeded, match="total cap"):
        call(fake_http(lambda r: httpx.Response(200, json=reply())), tmp_path)


def test_an_empty_answer_is_billed_and_logged_then_refused(tmp_path):
    http = fake_http(lambda r: httpx.Response(200, json=reply(content="  ")))
    with pytest.raises(ValueError, match="empty answer"):
        call(http, tmp_path)
    assert len(llm.read_ledger(tmp_path / "ledger.jsonl")) == 1


def test_balance_and_reconcile(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    body = {
        "is_available": True,
        "balance_infos": [
            {"currency": "CNY", "total_balance": "46.67"},
            {"currency": "USD", "total_balance": "0.00"},
        ],
    }
    assert llm.balance(fake_http(lambda r: httpx.Response(200, json=body))) == {
        "CNY": 46.67,
        "USD": 0.0,
    }
    assert llm.reconcile(ledger) is None

    llm.record_balance(ledger, {"CNY": 46.67}, "before")
    llm.append_ledger(ledger, {"type": "call", "cost_usd": 0.01})
    llm.append_ledger(ledger, {"type": "call", "cost_usd": 0.02})
    llm.record_balance(ledger, {"CNY": 46.50}, "after")
    llm.append_ledger(ledger, {"type": "call", "cost_usd": 0.5})  # after the last snapshot

    result = llm.reconcile(ledger)
    assert result["calls"] == 2
    assert result["estimated_usd"] == pytest.approx(0.03)
    assert result["balance_drop"]["CNY"] == pytest.approx(0.17)

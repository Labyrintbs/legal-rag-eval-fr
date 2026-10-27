"""DeepSeek chat calls with a price table, a cost ledger and spending caps."""

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

BASE_URL = "https://api.deepseek.com"
LEDGER = Path("data/llm_ledger.jsonl")

# USD per 1M tokens at peak: (input cache hit, input cache miss, output); off-peak is half.
# Snapshot of https://api-docs.deepseek.com/quick_start/pricing, read 2026-10-27.
PEAK_PRICES = {
    "deepseek-flash": (0.006, 0.30, 1.20),
    "deepseek-v4-pro": (0.044, 1.32, 3.96),
}
PEAK_HOURS_UTC = (1, 2, 3, 6, 7, 8, 9)

# Upper bound for the pre-call estimate; the pilot compares it with the billed prompt_tokens.
TOKENS_PER_CHAR = 0.5


class BudgetExceeded(Exception):
    pass


@dataclass
class Budget:
    run_cap: float
    total_cap: float
    spent: float = 0.0


def is_peak(when: datetime) -> bool:
    # Chinese public holidays are off-peak too; not modelled, so the cost is over-estimated then.
    return when.astimezone(UTC).weekday() < 5 and when.astimezone(UTC).hour in PEAK_HOURS_UTC


def cost_usd(model: str, hit: int, miss: int, output: int, when: datetime) -> float:
    hit_price, miss_price, out_price = PEAK_PRICES[model]
    factor = 1.0 if is_peak(when) else 0.5
    return factor * (hit * hit_price + miss * miss_price + output * out_price) / 1e6


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) * TOKENS_PER_CHAR)


def worst_case_cost(model: str, prompt_tokens: int, max_tokens: int) -> float:
    """Peak price, every input token a cache miss, the whole `max_tokens` generated."""
    _, miss_price, out_price = PEAK_PRICES[model]
    return (prompt_tokens * miss_price + max_tokens * out_price) / 1e6


def read_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append_ledger(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def ledger_total(path: Path) -> float:
    return sum(e["cost_usd"] for e in read_ledger(path) if e["type"] == "call")


def ensure_within_budget(budget: Budget, ledger_spent: float, worst_case: float) -> None:
    if budget.spent + worst_case > budget.run_cap:
        raise BudgetExceeded(
            f"run cap {budget.run_cap}: spent {budget.spent:.4f} + worst case {worst_case:.4f}"
        )
    if ledger_spent + worst_case > budget.total_cap:
        raise BudgetExceeded(
            f"total cap {budget.total_cap}: spent {ledger_spent:.4f} + worst case {worst_case:.4f}"
        )


def make_http(api_key: str, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=120,
        transport=transport,
    )


def chat(
    http: httpx.Client,
    ledger: Path,
    budget: Budget,
    label: str,
    model: str,
    messages: list[dict],
    max_tokens: int,
    thinking: bool = False,
    json_mode: bool = True,
) -> str:
    """One call, never retried. Raises BudgetExceeded before sending if the worst case does not fit."""
    prompt_tokens = estimate_tokens("".join(m["content"] for m in messages))
    worst = worst_case_cost(model, prompt_tokens, max_tokens)
    ensure_within_budget(budget, ledger_total(ledger), worst)

    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "thinking": {"type": "enabled" if thinking else "disabled"},
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    response = http.post("/chat/completions", json=body)
    response.raise_for_status()
    data = response.json()

    usage = data["usage"]
    now = datetime.now(UTC)
    cost = cost_usd(
        model,
        usage["prompt_cache_hit_tokens"],
        usage["prompt_cache_miss_tokens"],
        usage["completion_tokens"],
        now,
    )
    budget.spent += cost
    # Written before the content is checked: an empty answer is still billed.
    append_ledger(
        ledger,
        {
            "type": "call",
            "time": now.isoformat(timespec="seconds"),
            "label": label,
            "model": model,
            "estimated_prompt_tokens": prompt_tokens,
            "prompt_tokens": usage["prompt_tokens"],
            "cache_hit_tokens": usage["prompt_cache_hit_tokens"],
            "completion_tokens": usage["completion_tokens"],
            "reasoning_tokens": usage.get("completion_tokens_details", {}).get("reasoning_tokens"),
            "cost_usd": cost,
            "request_id": data.get("id"),
        },
    )
    content = data["choices"][0]["message"]["content"]
    if not content or not content.strip():
        raise ValueError(f"empty answer from {model} (billed {cost:.6f} USD)")
    return content


def balance(http: httpx.Client) -> dict[str, float]:
    response = http.get("/user/balance")
    response.raise_for_status()
    return {b["currency"]: float(b["total_balance"]) for b in response.json()["balance_infos"]}


def record_balance(ledger: Path, balances: dict[str, float], label: str) -> None:
    now = datetime.now(UTC).isoformat(timespec="seconds")
    append_ledger(ledger, {"type": "balance", "time": now, "label": label, "balances": balances})


def reconcile(ledger: Path) -> dict | None:
    """Estimated cost of the calls between the last two balance snapshots, against the balance drop."""
    entries = read_ledger(ledger)
    snapshots = [i for i, e in enumerate(entries) if e["type"] == "balance"]
    if len(snapshots) < 2:
        return None
    first, last = snapshots[-2], snapshots[-1]
    calls = [e for e in entries[first:last] if e["type"] == "call"]
    estimated = sum(e["cost_usd"] for e in calls)
    before, after = entries[first]["balances"], entries[last]["balances"]
    drop = {c: before[c] - after[c] for c in before}
    return {"calls": len(calls), "estimated_usd": estimated, "balance_drop": drop}

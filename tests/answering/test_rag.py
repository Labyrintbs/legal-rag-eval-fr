import json
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("llama_index.core")

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, TextNode

from legalrag.answering import answer, limits, rag, search, trace

TRIAL = ("Le contrat de travail à durée indéterminée peut comporter une période d'essai dont la durée maximale est : "
         "1° Pour les ouvriers et les employés, de deux mois ; 2° Pour les agents de maîtrise et les techniciens, de trois mois ; "
         "3° Pour les cadres, de quatre mois.")
PROMPT = {"system": "Réponds en json.", "user": "Extraits :\n{context}\n\nQuestion : {question}\n"}


def node(similarity=0.7, label="L1221-19", text=TRIAL):
    return NodeWithScore(node=TextNode(id_=f"{label}#0", text=text, metadata={
        "label": label, "chunk_index": 0, "header": f"Code du travail, article {label}.", "section_path": "Titre II",
        "url": f"https://example/{label}"}), score=similarity)


class FakeRetriever(BaseRetriever):
    def __init__(self, nodes):
        super().__init__()
        self.nodes = nodes

    def _retrieve(self, query_bundle):
        return self.nodes


class FakeLLM:
    def __init__(self, reply=None, error=None, usage=(1100, 90, 1000), served=None):
        self.reply, self.error, self.served, self.calls = reply, error, served, []
        self.usage = SimpleNamespace(prompt_tokens=usage[0], completion_tokens=usage[1], prompt_cache_hit_tokens=usage[2])

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self.error:
            raise self.error
        return SimpleNamespace(message=SimpleNamespace(content=self.reply), raw=SimpleNamespace(usage=self.usage, model=self.served))


def engine(nodes, llm, **changes):
    settings = {"model": "deepseek-flash", "prompt_id": "answer.v1"} | changes
    return rag.AnswerEngine(retriever=FakeRetriever(nodes), postprocessor=rag.NumberUnits(), llm=llm, prompt=PROMPT, **settings)


def ask(nodes, llm, **changes):
    return engine(nodes, llm, **changes).query("Quelle durée pour un cadre ?").metadata["result"]


GOOD = json.dumps({"refusal": False, "claims": [{"text": "Quatre mois pour un cadre.", "sources": ["1.4"]}]})


def test_a_good_reply_becomes_an_answer_with_the_stored_passage_and_the_cost_of_the_call():
    llm = FakeLLM(GOOD)
    result = ask([node(), node(0.65, "L1221-20", "Le renouvellement est possible une fois.")], llm)
    assert result.outcome == "answered" and "Quatre mois pour un cadre. [1]" in result.text
    assert "3° Pour les cadres, de quatre mois." in result.text
    messages, kwargs = llm.calls[0]
    assert kwargs == {"response_format": {"type": "json_object"}}
    assert "[1.4] 3° Pour les cadres, de quatre mois." in messages[1].content and "[Source 2]" in messages[1].content
    assert (result.tokens_in, result.tokens_out, result.tokens_cached) == (1100, 90, 1000)
    peak = 1.0 if rag.costs.is_peak(datetime.now(UTC)) else 0.5  # off-peak calls cost half
    assert result.cost_usd == pytest.approx((1000 * 0.006 + 100 * 0.30 + 90 * 1.20) / 1e6 * peak)


def test_cached_tokens_come_from_either_usage_form():
    openai_style = SimpleNamespace(prompt_tokens=1100, completion_tokens=90, prompt_tokens_details=SimpleNamespace(cached_tokens=800))
    assert answer.usage_of(openai_style) == (1100, 90, 800)
    assert answer.usage_of(SimpleNamespace(prompt_tokens=1100, completion_tokens=90, prompt_tokens_details=None)) == (1100, 90, None)
    assert answer.usage_of(SimpleNamespace(prompt_tokens=5, completion_tokens=1, prompt_cache_hit_tokens=3)) == (5, 1, 3)
    assert answer.usage_of(None) == (None, None, None)


class ProviderError(Exception):
    """What the model client raises for an HTTP error: a status code and the response with its headers."""

    def __init__(self, status_code, headers=None):
        super().__init__(f"HTTP {status_code}")
        self.status_code, self.response = status_code, SimpleNamespace(headers=headers or {})


def test_a_provider_refusal_for_rate_is_a_busy_service_with_the_wait_it_names_and_keeps_the_articles():
    result = ask([node()], FakeLLM(error=ProviderError(429, {"x-ratelimit-reset-tokens": "7s212ms"})))
    assert (result.outcome, result.status, result.retry_after, result.error) == ("llm_error", 503, 8, "ProviderError")
    assert result.hits


@pytest.mark.parametrize("headers, wait", [
    ({"x-ratelimit-reset-tokens": "1m3s"}, 60),  # never more than a minute
    ({"x-ratelimit-reset-tokens": "198ms"}, 1),  # never less than a second
    ({"retry-after": "7"}, 7),
    ({"retry-after": "7", "x-ratelimit-reset-tokens": "30s"}, 7),  # Retry-After first
    ({"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}, None),  # a date is not read
    ({}, None),
])
def test_the_wait_comes_from_retry_after_or_the_token_limit_reset(headers, wait):
    assert rag.wait_of(ProviderError(429, headers)) == wait


@pytest.mark.parametrize("error", [ProviderError(401), ProviderError(404), ProviderError(500), TimeoutError("slow")])
def test_any_other_failure_of_the_model_is_a_502_without_a_wait(error):
    result = ask([node()], FakeLLM(error=error))
    assert (result.outcome, result.status, result.retry_after) == ("llm_error", 502, None)


def test_a_run_of_failures_other_than_a_busy_provider_makes_the_model_side_failing_until_a_call_gets_an_answer():
    pulse = rag.ModelPulse()
    for _ in range(5):
        ask([node()], FakeLLM(error=ProviderError(429)), pulse=pulse)
    assert not pulse.failing  # a busy provider is not a failure
    for _ in range(rag.FAILING_AFTER):
        ask([node()], FakeLLM(error=ProviderError(401)), pulse=pulse)
    assert pulse.failing and pulse.last_error == "ProviderError"
    ask([node()], FakeLLM(GOOD), pulse=pulse)
    assert not pulse.failing


def test_a_reply_naming_another_model_than_the_one_asked_for_is_kept_until_a_restart_and_warned_once(caplog):
    pulse = rag.ModelPulse()
    ask([node()], FakeLLM(GOOD, served="deepseek-flash"), pulse=pulse)
    assert pulse.other_model is None
    with caplog.at_level("WARNING", logger=rag.log.name):
        ask([node()], FakeLLM(GOOD, served="replacement-1"), pulse=pulse)
        ask([node()], FakeLLM(GOOD, served="replacement-1"), pulse=pulse)
    assert pulse.other_model == "replacement-1"
    assert [r.getMessage() for r in caplog.records] == ["the provider answered with model 'replacement-1', not the 'deepseek-flash' that was asked for"]
    ask([node()], FakeLLM(GOOD, served="deepseek-flash"), pulse=pulse)
    assert pulse.other_model == "replacement-1"  # not cleared by a later reply that matches: someone must look


def test_a_reply_without_a_model_name_is_not_judged():
    pulse = rag.ModelPulse()
    ask([node()], FakeLLM(GOOD, served=None), pulse=pulse)
    assert pulse.other_model is None


def test_a_weak_search_never_calls_the_model():
    llm = FakeLLM(error=AssertionError("must not be called"))
    result = ask([node(0.54)], llm)
    assert result.outcome == "refused_weak_retrieval" and "0.54" in result.reason and llm.calls == []
    assert ask([], FakeLLM(GOOD)).outcome == "refused_weak_retrieval"


class FakeGate:
    def __init__(self, verdict):
        self.verdict, self.clients = verdict, []

    def check(self, client):
        self.clients.append(client)
        return self.verdict


def respond(nodes, llm, gate, client="c1", **changes):
    return engine(nodes, llm, gate=gate, **changes).respond("Quelle durée pour un cadre ?", client).metadata["result"]


def test_a_limited_request_never_calls_the_model_and_still_returns_the_articles():
    llm = FakeLLM(error=AssertionError("must not be called"))
    for verdict, outcome in ((limits.Decision(False, "rate_limited", "too many", 429, 42), "rate_limited"),
                             (limits.Decision(False, "llm_disabled", "switched off", 503), "llm_disabled")):
        gate = FakeGate(verdict)
        result = respond([node(), node(0.65, "L1221-20")], llm, gate)
        assert (result.outcome, result.status, result.retry_after) == (outcome, verdict.status, verdict.retry_after)
        assert [h.label for h in result.hits] == ["L1221-19", "L1221-20"] and verdict.reason in result.text
        assert gate.clients == ["c1"] and llm.calls == []


def test_an_allowed_request_reaches_the_model_and_a_weak_search_skips_the_gate():
    gate = FakeGate(limits.ALLOWED)
    result = respond([node()], FakeLLM(GOOD), gate)
    assert result.outcome == "answered" and result.status == 200 and gate.clients == ["c1"]
    weak = FakeGate(limits.Decision(False, "llm_disabled", "off", 503))
    assert respond([node(0.40)], FakeLLM(GOOD), weak).outcome == "refused_weak_retrieval" and weak.clients == []


def test_every_failure_of_the_call_or_the_reply_has_its_own_outcome():
    assert ask([node()], FakeLLM(error=TimeoutError("slow"))).outcome == "llm_error"
    assert ask([node()], FakeLLM(error=TimeoutError("slow"))).error == "TimeoutError"
    assert ask([node()], FakeLLM("not json")).outcome == "parse_error"
    assert ask([node()], FakeLLM('{"claims": "oops"}')).outcome == "parse_error"
    nothing = json.dumps({"refusal": False, "claims": [{"text": "x", "sources": ["9.9"]}]})
    assert ask([node()], FakeLLM(nothing)).outcome == "invalid_citation"
    refusal = json.dumps({"refusal": True, "reason": "not covered", "claims": []})
    result = ask([node()], FakeLLM(refusal))
    assert result.outcome == "refused_by_model" and result.reason == "not covered"


def test_an_unknown_model_has_no_cost_and_the_development_ledger_gets_a_line_only_when_asked(tmp_path, monkeypatch):
    monkeypatch.setattr(rag.costs, "LEDGER", tmp_path / "ledger.jsonl")
    assert ask([node()], FakeLLM(GOOD), model="other-model").cost_usd is None
    assert not (tmp_path / "ledger.jsonl").exists()
    ask([node()], FakeLLM(GOOD), ledger_label="pilot-x")
    line = json.loads((tmp_path / "ledger.jsonl").read_text())
    assert line["type"] == "call" and line["label"] == "pilot-x" and line["cache_hit_tokens"] == 1000 and line["cost_usd"] > 0


def test_the_trace_of_a_result_holds_scores_cited_units_and_tokens():
    result = ask([node(), node(0.65, "L1221-20", "Le renouvellement est possible une fois.")], FakeLLM(GOOD))
    t = answer.to_trace(result, "rid", "fr", "Quelle durée pour un cadre ?", "answer", "deepseek-flash", "answer.v1", "hash", "abc", "default")
    assert t.outcome == "answered" and t.request_id == "rid" and t.tokens_in == 1100 and t.model == "deepseek-flash"
    assert t.retrieved == [{"label": "L1221-19", "chunk_index": 0, "score": 0.7}, {"label": "L1221-20", "chunk_index": 0, "score": 0.65}]
    assert t.cited == [{"label": "L1221-19", "chunk_index": 0, "unit": 4}] and t.answer.startswith("Quatre mois")
    assert t.outcome in trace.OUTCOMES
    refused = answer.to_trace(ask([node(0.4)], FakeLLM(GOOD)), "r2", "fr", "q", "answer", None, None)
    assert refused.answer is None and refused.refusal_reason.startswith("top similarity")


def test_the_retriever_wraps_the_search_and_keeps_the_best_chunk_of_each_article(monkeypatch):
    hits = [search.Hit("L1", 0, "h1", "texte un", 0.8, "p1", "u1"), search.Hit("art 17", 2, "h2", "texte deux", 0.7, "p2", "u2")]
    monkeypatch.setattr(search, "top_chunks", lambda conn, run, lang, vector, k, model: hits)

    @contextmanager
    def connect():
        yield None

    embedder = SimpleNamespace(encode_queries=lambda texts, batch: np.ones((len(texts), 4), dtype=np.float32))
    nodes = rag.LegalRetriever(connect, 1, embedder, "fr").retrieve("question")
    assert [(n.node.metadata["label"], n.node.metadata["chunk_index"], n.score) for n in nodes] == [("L1", 0, 0.8), ("art 17", 2, 0.7)]
    assert rag.hits_of(nodes)[1] == hits[1]


def test_with_the_article_rule_the_named_article_comes_first_and_is_marked(monkeypatch):
    hits = [search.Hit("L1", 0, "h1", "texte un", 0.8, "p1", "u1"), search.Hit("L1221-13", 1, "h2", "texte deux", 0.5, "p2", "u2")]
    named = [search.Hit("L1221-13", 1, "h2", "texte deux", 0.5, "p2", "u2")]
    monkeypatch.setattr(search, "top_chunks", lambda conn, run, lang, vector, k, model: hits)
    monkeypatch.setattr(search, "named_chunks", lambda conn, run, lang, vector, keys, model: named if keys else [])

    @contextmanager
    def connect():
        yield None

    embedder = SimpleNamespace(encode_queries=lambda texts, batch: np.ones((len(texts), 4), dtype=np.float32))
    plain = rag.LegalRetriever(connect, 1, embedder, "fr")
    ruled = rag.LegalRetriever(connect, 1, embedder, "fr", article_rule=True)
    nodes = ruled.retrieve("Que dit l'article L. 1221-13 ?")
    assert [(n.node.metadata["label"], n.node.metadata["named"]) for n in nodes] == [("L1221-13", True), ("L1", False)]
    assert rag.names_article(nodes)
    assert not rag.names_article(ruled.retrieve("Quelle durée ?"))  # no number: the plain ranking
    assert [n.node.metadata["label"] for n in plain.retrieve("Que dit l'article L1221-13 ?")] == ["L1", "L1221-13"]  # rule off


def test_a_named_article_is_answered_even_when_the_search_is_weak_and_an_unnamed_weak_search_is_still_refused():
    weak = node(0.50)
    weak.node.metadata["named"] = True
    llm = FakeLLM(GOOD)
    assert ask([weak], llm).outcome == "answered" and len(llm.calls) == 1
    llm = FakeLLM(GOOD)
    assert ask([node(0.50)], llm).outcome == "refused_weak_retrieval" and llm.calls == []


def test_the_post_processor_adds_the_units_without_touching_the_text():
    nodes = rag.NumberUnits().postprocess_nodes([node()])
    assert nodes[0].node.text == TRIAL and len(nodes[0].node.metadata["units"]) == 4
    assert rag.sources_of(nodes)[0].units[3].lead == 0

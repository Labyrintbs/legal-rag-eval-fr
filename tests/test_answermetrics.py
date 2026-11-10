from legalrag import answermetrics as am

TEXT = "Quatre mois. [1]\nRenouvelable. [1]\n\n[1] L1221-19 - Quatre mois pour les cadres."


def row(id, kind="answerable", outcome="answered", cited=("L1",), gold=("L1",), primary=("L1",), top5=("L1", "L2"), **changes):
    base = {"id": id, "kind": kind, "outcome": outcome, "text": TEXT, "cited": list(cited), "gold": list(gold),
            "primary": list(primary), "top5": list(top5), "cost_usd": 0.0004, "llm_ms": 1500, "tokens_in": 2000, "tokens_out": 200}
    return base | changes


def test_claim_items_are_the_claims_of_answered_rows_only():
    rows = [row("a1"), row("r1", outcome="refused_by_model"), row("a2")]
    assert [i.key for i in am.claim_items(rows)] == ["a1|claim0", "a1|claim1", "a2|claim0", "a2|claim1"]


def test_faithfulness_counts_claims_and_answers_and_keeps_the_judge_errors_apart():
    verdicts = [{"key": "a1|claim0", "label": "supported"}, {"key": "a1|claim1", "label": "partly"},
                {"key": "a2|claim0", "label": "supported"}, {"key": "a2|claim1", "label": "not supported"},
                {"key": "a3|claim0", "error": "ValueError"}]
    f = am.faithfulness(verdicts)
    assert f["claims"] == 4 and f["judge_errors"] == 1 and f["counts"] == {"supported": 2, "partly": 1, "not supported": 1}
    assert (f["answers"], f["answers_all_supported"], f["answers_with_not_supported"]) == (2, 0, 1)


def test_citations_count_gold_and_primary_among_answered_answerable_questions():
    rows = [row("a1"), row("a2", cited=("L9", "L1")), row("a3", cited=("L9",)), row("a4", cited=("L2",), primary=("L3",)),
            row("r1", outcome="refused_by_model"), row("f1", kind="false_premise")]
    c = am.citations(rows)
    assert (c["answers"], c["cite_gold"], c["cite_primary"], c["cited_articles"], c["cited_gold"]) == (4, 2, 2, 5, 2)


def test_refusals_separate_retrieval_misses_from_refusals_with_evidence():
    rows = [row("a1"), row("r1", outcome="refused_by_model", top5=("L2",)), row("r2", outcome="refused_by_model"),
            row("u1", kind="unanswerable", outcome="refused_weak_retrieval", gold=()),
            row("f1", kind="false_premise", gold=()), row("s1", kind="underspecified")]
    r = am.refusals(rows)
    assert (r["answerable"], r["answered"], r["refused"]) == (3, 1, 2)
    assert (r["refused_retrieval_miss"], r["refused_with_evidence"]) == (1, 1)
    assert (r["no_answer_expected"], r["correctly_refused"], r["underspecified_answered"]) == (2, 1, 1)


def test_cost_sums_the_calls_and_ignores_rows_without_one():
    rows = [row("a1"), row("a2", llm_ms=3000), row("r1", outcome="refused_weak_retrieval", cost_usd=None, llm_ms=None)]
    c = am.cost(rows)
    assert c["calls"] == 2 and c["cost_usd"] == 0.0008 and c["tokens_in"] == 4000 and c["llm_ms_median"] == 3000

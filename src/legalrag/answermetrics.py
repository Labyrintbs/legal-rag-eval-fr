"""Metrics of the answers of a pilot run (step 0d, decision 17): faithfulness from the claim judge, citations
and refusals counted from the pilot rows. Completeness is not measured: no validated way to judge it.
"""

from collections import defaultdict

from legalrag import claimjudge, labelsheet

ANSWERABLE = "answerable"
NO_ANSWER_EXPECTED = ("unanswerable", "false_premise")


def claim_items(rows: list[dict]) -> list[claimjudge.Item]:
    """Every claim of every answered row, keyed `<id>|claim<N>` as in the label files; no human label."""
    return [claimjudge.Item(f"{r['id']}|claim{i}", c.text, c.passages, "")
            for r in rows if r["outcome"] == "answered" for i, c in enumerate(labelsheet.parse_answer(r["text"]))]


def faithfulness(verdicts: list[dict]) -> dict:
    """Shares of supported, partly and not supported claims, and of answers all of whose claims are supported.
    The judge flags about a quarter of the good claims (decision 16): read the shares as lower bounds."""
    judged = [v for v in verdicts if v.get("label")]
    counts = {label: sum(v["label"] == label for v in judged) for label in claimjudge.LABELS}
    by_answer = defaultdict(list)
    for v in judged:
        by_answer[v["key"].split("|")[0]].append(v["label"])
    return {"claims": len(judged), "judge_errors": len(verdicts) - len(judged), "counts": counts,
            "answers": len(by_answer), "answers_all_supported": sum(all(x == "supported" for x in xs) for xs in by_answer.values()),
            "answers_with_not_supported": sum("not supported" in xs for xs in by_answer.values())}


def citations(rows: list[dict]) -> dict:
    """For the answered answerable questions: how many cite a gold or a primary gold article, and the share of the
    cited articles that are gold. A cited article that is not gold may still be right: the gold lists are not complete."""
    done = [r for r in rows if r["kind"] == ANSWERABLE and r["outcome"] == "answered"]
    cited = sum(len(r["cited"]) for r in done)
    return {"answers": len(done), "cite_gold": sum(bool(set(r["cited"]) & set(r["gold"])) for r in done),
            "cite_primary": sum(bool(set(r["cited"]) & set(r["primary"])) for r in done),
            "cited_articles": cited, "cited_gold": sum(len(set(r["cited"]) & set(r["gold"])) for r in done)}


def refusals(rows: list[dict]) -> dict:
    """Answerable questions answered or refused (a refusal is a retrieval miss when no gold article was in the
    top 5, and a model refusal despite evidence when one was); the others (unanswerable, false premise)
    refused or answered; the underspecified ones."""
    answerable = [r for r in rows if r["kind"] == ANSWERABLE]
    refused = [r for r in answerable if r["outcome"] != "answered"]
    missed = [r for r in refused if not set(r["top5"]) & set(r["gold"])]
    others = [r for r in rows if r["kind"] in NO_ANSWER_EXPECTED]
    return {"answerable": len(answerable), "answered": len(answerable) - len(refused), "refused": len(refused),
            "refused_retrieval_miss": len(missed), "refused_with_evidence": len(refused) - len(missed),
            "no_answer_expected": len(others), "correctly_refused": sum(r["outcome"] != "answered" for r in others),
            "underspecified_answered": sum(r["kind"] == "underspecified" and r["outcome"] == "answered" for r in rows)}


def cost(rows: list[dict]) -> dict:
    """Tokens, cost and model time of the answer calls (rows without a call have no cost)."""
    called = [r for r in rows if r.get("cost_usd") is not None]
    times = sorted(r["llm_ms"] for r in called if r.get("llm_ms") is not None)
    return {"calls": len(called), "cost_usd": sum(r["cost_usd"] for r in called),
            "tokens_in": sum(r["tokens_in"] or 0 for r in called), "tokens_out": sum(r["tokens_out"] or 0 for r in called),
            "llm_ms_median": times[len(times) // 2] if times else None}

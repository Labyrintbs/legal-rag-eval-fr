import pytest

from legalrag.evaluation import claimjudge, labelsheet

TEXT = "Quatre mois pour un cadre. [1]\nRenouvelable une fois. [2]\n\n[1] L1221-19 - Quatre mois pour les cadres.\n[2] L1221-20 - Une fois."
ROWS = [{"id": "a1", "text": TEXT}]
CHECKS = [{"id": "check-01", "claim": labelsheet.Claim("Six mois pour un cadre.", [("L1221-19", "Quatre mois pour les cadres.")])}]
PROMPT = {"system": "Juge.", "user": "Claim:\n{claim}\n\nPassages:\n{passages}"}


def test_collect_finds_each_labelled_claim_edited_or_not_and_skips_other_choices():
    labels = {"a1|claim1": "supported", "check-01|claim0": "not supported", "a1|answer": "yes", "a1|note": "x"}
    items = claimjudge.collect(labels, ROWS, CHECKS)
    assert [(i.key, i.claim, i.human) for i in items] == [("a1|claim1", "Renouvelable une fois.", "supported"),
                                                           ("check-01|claim0", "Six mois pour un cadre.", "not supported")]
    assert items[0].passages == [("L1221-20", "Une fois.")] and items[1].passages == [("L1221-19", "Quatre mois pour les cadres.")]


def test_the_judge_sees_the_claim_and_its_passages_and_never_the_human_label():
    (item,) = claimjudge.collect({"check-01|claim0": "not supported"}, ROWS, CHECKS)
    system, user = claimjudge.messages(PROMPT, item)
    assert "Six mois pour un cadre." in user["content"] and "[L1221-19] Quatre mois pour les cadres." in user["content"]
    assert "not supported" not in system["content"] + user["content"]


def test_parse_reads_a_verdict_and_refuses_anything_else():
    assert claimjudge.parse('{"reason": "7 500 au lieu de 3 750", "label": "Not Supported"}') == ("not supported", "7 500 au lieu de 3 750")
    for bad in ('{"label": "maybe"}', '{"reason": "x"}', "not json"):
        with pytest.raises(ValueError):
            claimjudge.parse(bad)


def test_kappa_is_one_for_full_agreement_zero_for_chance_and_none_when_a_label_is_never_used():
    same = [("supported", "supported"), ("partly", "partly"), ("not supported", "not supported")]
    assert claimjudge.kappa(same) == pytest.approx(1.0)
    assert claimjudge.kappa([("supported", "supported"), ("supported", "not supported"),
                             ("not supported", "supported"), ("not supported", "not supported")]) == pytest.approx(0.0)
    assert claimjudge.kappa([("supported", "supported")] * 3) is None and claimjudge.kappa([]) is None


def test_the_report_counts_the_errors_caught_and_the_good_claims_flagged():
    pairs = [("not supported", "not supported"), ("not supported", "supported"), ("partly", "partly"),
             ("supported", "supported"), ("supported", "partly")]
    r = claimjudge.report(pairs)
    assert (r["n"], r["errors"], r["errors_caught"], r["good"], r["good_flagged"]) == (5, 3, 2, 2, 1)
    assert r["agreement"] == pytest.approx(3 / 5) and r["confusion"]["not supported"]["supported"] == 1

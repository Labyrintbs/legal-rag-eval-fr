from legalrag import labelsheet

TEXT = (
    "Quatre mois pour un cadre. [1]\n"
    "Le renouvellement est possible, selon le texte. [2][3]\n"
    "\n"
    "[1] L1221-19 - 3° Pour les cadres, de quatre mois.\n"
    "[2] art 17 - Le droit à l'effacement.\n"
    "[3] L1221-20 - Le renouvellement est possible une fois."
)


def row(id, outcome="answered", kind="answerable", cited=("L1221-19",), **changes):
    base = {"id": id, "kind": kind, "outcome": outcome, "text": TEXT, "cited": list(cited), "gold": ["L1221-19"],
            "reason": None, "question": "Quelle durée ?"}
    return base | changes


def test_claims_come_with_the_passages_they_cite():
    first, second = labelsheet.parse_answer(TEXT)
    assert first == labelsheet.Claim("Quatre mois pour un cadre.", [("L1221-19", "3° Pour les cadres, de quatre mois.")])
    assert [label for label, _ in second.passages] == ["art 17", "L1221-20"]


def test_a_passage_with_several_lines_stays_with_its_note():
    text = "Une règle. [1]\n\n[1] art 5 - Premier point;\na) second point;\n[2] suite"
    (claim,) = labelsheet.parse_answer(text)
    assert claim.passages == [("art 5", "Premier point;\na) second point;")]


def test_pick_keeps_every_refusal_and_odd_kind_and_samples_the_plain_answers():
    rows = [row(f"a{i}") for i in range(10)] + [row(f"g{i}", cited=("art 17",)) for i in range(10)]
    rows += [row("r1", outcome="refused_by_model", reason="no"), row("f1", kind="false_premise"), row("u1", kind="underspecified")]
    sample = labelsheet.pick(rows, answered=10, gdpr_share=0.3)
    ids = [r["id"] for r in sample]
    assert {"r1", "f1", "u1"} <= set(ids) and len(ids) == 13
    assert sum(i.startswith("g") for i in ids) == 3
    assert ids == [r["id"] for r in rows if r["id"] in ids] and ids == [r["id"] for r in labelsheet.pick(rows, 10, 0.3)]


def test_the_sheet_has_a_radio_group_per_claim_and_per_answer_and_escapes_the_text():
    page = labelsheet.render([row("a1", question="Vrai <b>?</b>"), row("r1", outcome="refused_by_model", reason="no")], "t")
    assert page.count('name="a1|claim') == 2 * 3 and page.count('name="a1|answer"') == 3
    assert page.count('name="r1|refusal"') == 3 and "Vrai &lt;b&gt;?&lt;/b&gt;" in page and "<b>?</b>" not in page

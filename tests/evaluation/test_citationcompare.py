from legalrag.evaluation import answermetrics, labelsheet
from legalrag.evaluation import citationcompare as cc

SOURCES = [("L1221-19", "Quatre mois pour les cadres."), ("L1221-20", "Renouvelable une fois.")]


def test_sentences_are_split_with_the_source_numbers_they_cite():
    text = "Quatre mois pour un cadre [1]. Renouvelable une fois [2][1]. Voir la convention.\nEt aussi [1, 2]."
    cited, uncited = cc.cited_sentences(text, 2)
    assert cited == [("Quatre mois pour un cadre.", [1]), ("Renouvelable une fois.", [2, 1]), ("Et aussi.", [1, 2])]
    assert uncited == 1


def test_marks_written_as_source_n_count_as_citations():
    cited, uncited = cc.cited_sentences("Quatre mois [Source 1]. Renouvelable [Sources 1, 2].", 2)
    assert cited == [("Quatre mois.", [1]), ("Renouvelable.", [1, 2])] and uncited == 0


def test_numbers_that_name_no_source_are_dropped_and_a_sentence_left_with_none_is_uncited():
    cited, uncited = cc.cited_sentences("Une idée [3]. Une autre [1][9].", 2)
    assert cited == [("Une autre.", [1])] and uncited == 1


def test_the_source_line_added_by_the_engine_is_removed():
    assert cc.source_passage("Source 2:\nRenouvelable une fois.\n") == "Renouvelable une fois."


def test_the_rendered_answer_is_read_by_the_same_parser_as_our_answers():
    cited = [("Quatre mois pour un cadre.", [1]), ("Renouvelable.", [2, 1])]
    text = cc.render(cited, SOURCES)
    claims = labelsheet.parse_answer(text)
    assert [c.text for c in claims] == ["Quatre mois pour un cadre.", "Renouvelable."]
    assert [label for label, _ in claims[1].passages] == ["L1221-20", "L1221-19"]
    row = {"id": "q", "outcome": "answered", "text": text}
    assert [i.key for i in answermetrics.claim_items([row])] == ["q|claim0", "q|claim1"]

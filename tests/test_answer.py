import pytest

from legalrag import answer, search
from legalrag.answer import Claim, ModelAnswer

TRIAL = ("Le contrat de travail à durée indéterminée peut comporter une période d'essai dont la durée maximale est : "
         "1° Pour les ouvriers et les employés, de deux mois ; 2° Pour les agents de maîtrise et les techniciens, de trois mois ; "
         "3° Pour les cadres, de quatre mois.")


def hit(label="L1221-19", text=TRIAL, similarity=0.7, header="Code du travail, article L1221-19. Section 4 : Période d'essai."):
    return search.Hit(label, 0, header, text, similarity, "Titre II > Section 4 : Période d'essai", f"https://example/{label}")


def sources():
    return answer.make_sources([hit(), hit("L1221-20", "Le renouvellement est possible une fois. Il doit être expressément prévu.", 0.65, "")])


def test_the_best_chunk_of_each_article_is_kept_in_order():
    rows = [(0, "h", "a", "code_travail", "article", "L1", "p", "u", 0.9), (1, "h", "b", "code_travail", "article", "L1", "p", "u", 0.8),
            (0, "h", "c", "rgpd", "article", "17", "p", "u", 0.7), (0, "h", "d", "code_travail", "article", "L2", "p", "u", 0.6)]
    got = search.best_chunk_per_article(rows, k=3)
    assert [(h.label, h.text) for h in got] == [("L1", "a"), ("art 17", "c"), ("L2", "d")]
    assert len(search.best_chunk_per_article(rows, k=2)) == 2


def test_a_weak_search_is_refused_before_the_model():
    assert search.is_weak([]) and search.is_weak([hit(similarity=0.54)]) and not search.is_weak([hit(similarity=0.55)])
    assert search.WEAK_THRESHOLD == 0.55 and search.TOP_ARTICLES == 5


def test_the_context_numbers_every_unit_under_its_source():
    text = answer.context(sources())
    assert text.startswith("[Source 1] Code du travail, article L1221-19. Section 4")
    assert "[1.1] Le contrat de travail" in text and "[1.4] 3° Pour les cadres, de quatre mois." in text
    assert "[Source 2] L1221-20" in text and "[2.2] Il doit être expressément prévu." in text


def test_a_cited_list_item_is_resolved_to_its_stored_text_with_the_lead_in():
    out = answer.resolve(ModelAnswer(claims=[Claim(text="Quatre mois pour un cadre.", sources=["1.4"])]), sources())
    assert out.outcome == "answered"
    (text, citations), = out.claims
    assert text == "Quatre mois pour un cadre." and citations[0].label == "L1221-19" and citations[0].units == [4]
    assert citations[0].passage.startswith("Le contrat de travail") and citations[0].passage.endswith("3° Pour les cadres, de quatre mois.")
    assert "[…]" in citations[0].passage and citations[0].url == "https://example/L1221-19"


@pytest.mark.parametrize("raw", ["1.4", "[1.4]", "Source 1.4", " 1.4 "])
def test_ids_are_read_in_the_ways_a_model_writes_them(raw):
    assert answer.parse_id(raw) == (1, 4)
    assert answer.parse_id("none") is None


def test_ids_that_do_not_exist_are_dropped_and_a_claim_without_a_valid_id_is_dropped():
    out = answer.resolve(ModelAnswer(claims=[Claim(text="a", sources=["1.2", "1.99", "9.1"]), Claim(text="b", sources=["7.7"]),
                                             Claim(text="c", sources=[])]), sources())
    assert out.outcome == "answered" and [t for t, _ in out.claims] == ["a"]
    assert out.dropped_claims == 2 and out.dropped_ids == ("1.99", "9.1", "7.7")
    assert out.claims[0][1][0].units == [2]


def test_claims_with_no_valid_citation_make_a_refusal_never_an_uncited_answer():
    out = answer.resolve(ModelAnswer(claims=[Claim(text="a", sources=["8.8"])]), sources())
    assert out.outcome == "invalid_citation" and out.claims == []
    assert answer.resolve(ModelAnswer(), sources()).outcome == "refused_by_model"
    refused = answer.resolve(ModelAnswer(refusal=True, reason="not covered", claims=[Claim(text="x", sources=["1.1"])]), sources())
    assert refused.outcome == "refused_by_model" and refused.claims == [] and refused.reason == "not covered"


def test_claims_citing_two_sources_get_one_citation_each_and_the_text_shows_numbered_marks():
    out = answer.resolve(ModelAnswer(claims=[Claim(text="Quatre mois, renouvelable une fois.", sources=["1.4", "2.1"])]), sources())
    assert [c.label for c in out.claims[0][1]] == ["L1221-19", "L1221-20"]
    shown = answer.render(out)
    assert "Quatre mois, renouvelable une fois. [1][2]" in shown and "[2] L1221-20 - Le renouvellement est possible une fois." in shown
    assert answer.render(answer.Resolved("refused_by_model", [], "not covered")) == "(no answer: not covered)"

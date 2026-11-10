import json
from pathlib import Path

import pandas as pd
import pytest

from legalrag.answering.units import GAP, passage, split_units
from legalrag.corpus.sources import legi

TRIAL = ("Le contrat de travail à durée indéterminée peut comporter une période d'essai dont la durée maximale est : "
         "1° Pour les ouvriers et les employés, de deux mois ; 2° Pour les agents de maîtrise et les techniciens, de trois mois ; "
         "3° Pour les cadres, de quatre mois. Cette durée est renouvelable.")
GDPR = ("1. La personne concernée a le droit d'obtenir l'effacement, lorsque l'un des motifs suivants s'applique:\n"
        "a) les données ne sont plus nécessaires;\nb) la personne retire son consentement;\n\n"
        "2. Lorsque le responsable a rendu les données publiques, il prend des mesures raisonnables.")


def texts(text):
    return [text[u.start:u.end] for u in split_units(text)]


def test_a_numbered_list_gives_a_lead_in_and_one_unit_per_item():
    units = split_units(TRIAL)
    assert [TRIAL[u.start:u.end][:2] for u in units] == ["Le", "1°", "2°", "3°", "Ce"]
    assert [u.lead for u in units] == [None, 0, 0, 0, None]
    assert TRIAL[units[3].start:units[3].end] == "3° Pour les cadres, de quatre mois."


def test_a_cited_item_is_shown_with_its_lead_in_and_a_gap_marker():
    units = split_units(TRIAL)
    shown = passage(TRIAL, units, [4])
    assert shown == ("Le contrat de travail à durée indéterminée peut comporter une période d'essai dont la durée maximale est :"
                     + GAP + "3° Pour les cadres, de quatre mois.")
    assert passage(TRIAL, units, [2, 3, 4]) == TRIAL[:TRIAL.index(" Cette durée")]  # consecutive units read as in the source


def test_a_1_bis_item_does_not_break_the_list():
    text = "Cette cotisation n'est pas due dans les cas suivants : 1° Faute grave ; 1° bis Refus de modification ; 2° Départ à la retraite."
    assert [t[:6] for t in texts(text)] == ["Cette ", "1° Fau", "1° bis", "2° Dép"]


def test_references_to_items_are_not_lists():
    text = "Les dispositifs prévus aux 1° et 2° de l'article R. 4534-99 sont agencés de manière sûre."
    units = split_units(text)
    assert len(units) == 1 and units[0].lead is None


def test_gdpr_points_follow_their_lead_in_and_a_paragraph_number_is_not_a_unit():
    units = split_units(GDPR)
    assert [GDPR[u.start:u.end][:2] for u in units] == ["1.", "a)", "b)", "2."]
    assert [u.lead for u in units] == [None, 0, 0, None]
    assert passage(GDPR, units, [3]).startswith("1. La personne concernée") and passage(GDPR, units, [3]).endswith("consentement;")


def test_an_article_reference_does_not_end_a_sentence():
    text = "Voir l'article L. 8113-6 du code. Autre phrase."
    assert texts(text) == ["Voir l'article L. 8113-6 du code.", "Autre phrase."]


def test_empty_and_one_sentence_texts():
    assert split_units("") == [] and split_units("   ") == []
    assert texts("Une seule phrase sans point") == ["Une seule phrase sans point"]


@pytest.mark.parametrize("text", [TRIAL, GDPR, "A. B.\n\nC d\ne f.", "1° seul item sans liste. Et la suite.", "Liste : 1° a ; 2° b."])
def test_units_are_slices_in_order_with_only_whitespace_between_them(text):
    units, previous = split_units(text), 0
    for i, u in enumerate(units):
        assert 0 <= previous <= u.start < u.end <= len(text) and text[u.start:u.end] == text[u.start:u.end].strip()
        assert not text[previous:u.start].strip()
        assert u.lead is None or u.lead < i
        previous = u.end
    assert not text[previous:].strip()


def test_invariants_hold_on_the_real_articles_of_the_fixture():
    sample = legi.to_articles(pd.DataFrame(json.loads((Path(__file__).parents[1] / "fixtures" / "code_travail_sample.json").read_text())))
    assert sample
    for article in sample:
        body, previous = article.body_text, 0
        for u in split_units(body):
            assert u.start >= previous and not body[previous:u.start].strip()
            previous = u.end
        assert not body[previous:].strip()

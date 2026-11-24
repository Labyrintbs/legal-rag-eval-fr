"""Edge cases of the personal-data filter: ways to hide an identifier, texts that look like one and are not, and inputs
that could make the filter slow or break it."""

import random
import time

import pytest

from legalrag.answering import pii

BODY = "1850578006084"
NIR = f"{BODY}{97 - int(BODY) % 97:02d}"
IBAN = "FR14 2004 1010 0505 0001 3M02 606"


@pytest.mark.parametrize("hidden, kind", [
    ("jean.dupont@exa\u200bmple.com", "email"), ("jean‍.dupont@example.com", "email"), ("jean@example⁠.com", "email"),
    ("ｊｅａｎ＠ｅｘａｍｐｌｅ．ｃｏｍ", "email"), ("JEAN.DUPONT@EXAMPLE.COM", "email"), ("j+tag@sub.example.co.uk", "email"),
    ("06\u200b12 34 56 78", "phone"), ("０６ １２ ３４ ５６ ７８", "phone"), ("+33 6 12 34 56 78", "phone"),
    ("06 12 34 56 78", "phone"), ("(0033) 6 12 34 56 78".replace("(", "").replace(")", ""), "phone"),
    (IBAN.lower(), "iban"), (IBAN.replace(" ", ""), "iban"), (IBAN.replace(" ", "\u200b "), "iban"),
    ("4111\u200b 1111 1111 1111", "card"), ("４１１１ １１１１ １１１１ １１１１", "card"), ("4111-1111-1111-1111", "card"),
    (f"{NIR[0]} {NIR[1:3]}.{NIR[3:5]}.{NIR[5:7]} {NIR[7:10]} {NIR[10:13]} {NIR[13:]}", "nir"),
])
def test_an_identifier_hidden_by_invisible_characters_or_other_forms_is_still_found(hidden, kind):
    masked = pii.mask(f"Mon contact : {hidden}, merci.")
    assert kind in masked.kinds, hidden
    assert masked.text.startswith("Mon contact : [") and masked.text.endswith("], merci."), masked.text


@pytest.mark.parametrize("text", [
    "", " ", "\n\n", "?", "a", "@", "a@", "@b.fr", "06", "0612", "+33", "FR14", "4111 1111",
    "Article L1221-13-1 du Code du travail", "décret n° 2017-1387 du 22 septembre 2017", "arrêté du 8 août 2016",
    "2026-11-24", "24/11/2026", "24.11.2026 à 10 h 30", "1 234 567,89 €", "3,5 % de 12 500 euros", "SMIC : 1 801,80 €",
    "version 3.12.4 de Python", "adresse IP 192.168.0.1", "RFC 2822", "ISO 8601", "page 123 456", "numéro 12345",
    "le 1er janvier 2024", "du 01 au 15 mars", "entre 06h00 et 12h00", "L. 1221-13 et R. 1454-14", "R*3231-4",
])
def test_text_that_looks_like_an_identifier_but_is_not_is_left_alone(text):
    masked = pii.mask(text)
    assert masked.kinds == [] and masked.text == pii.normalise(text)


def test_masking_twice_changes_nothing_more():
    text = f"a@b.fr, 06 12 34 56 78, {IBAN}, 4111 1111 1111 1111, {NIR}"
    once = pii.mask(text)
    assert sorted(once.kinds) == ["card", "email", "iban", "nir", "phone"]
    assert pii.mask(once.text).text == once.text and pii.mask(once.text).kinds == []


def test_identifiers_next_to_each_other_or_in_a_url_are_all_found():
    masked = pii.mask("https://site.fr/?mail=a@b.fr&tel=0612345678;b@c.fr,06 12 34 56 78")
    assert masked.kinds.count("email") == 2 and masked.kinds.count("phone") == 2


def test_a_digit_run_longer_than_an_identifier_is_not_cut_into_one():
    assert pii.mask("0612345678901234").kinds == []  # 16 digits starting with 0: not a French phone number
    assert pii.mask("0612345678 9").text.startswith("[téléphone]")  # a number followed by a separate digit: the phone number is found
    assert pii.mask("9" * 40).kinds == []


@pytest.mark.parametrize("text", [
    "a" * 5000, "a." * 2500, "a@" * 2500, "1 " * 2500, "1" * 5000, "FR" + "1" * 5000, "FR14 " + "A1B2 " * 1000,
    "+" + "1" * 5000, "0" + " 12" * 2000, "a@b" + ".c" * 2500, "\u200b" * 5000, "é" * 5000, "@" * 5000, "-" * 5000,
])
def test_a_long_or_hostile_text_is_masked_quickly(text):
    started = time.perf_counter()
    pii.mask(text)
    assert time.perf_counter() - started < 1.0, text[:12]


def test_random_text_never_breaks_the_filter_and_masking_is_stable():
    rng = random.Random(20261124)
    alphabet = "0123456789 .-+@aAbB€é\u200b\n\t()FR"
    for _ in range(1500):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 80)))
        masked = pii.mask(text)
        assert pii.mask(masked.text).text == masked.text  # a second pass finds nothing new
        assert len(masked.text) <= len(pii.normalise(text)) + 40 * len(masked.kinds)  # a label is a few characters, never a blow-up


def test_a_question_that_is_only_an_identifier_becomes_a_label_and_is_still_a_text():
    assert pii.mask("a@b.fr").text == "[e-mail]"
    assert pii.mask("06 12 34 56 78").text == "[téléphone]"
    assert pii.mask(" \u200b ").text.strip() == ""

import pytest

from legalrag.answering import pii

BODY = "1850578006084"  # a made-up social security number: its key is computed, not copied from a person
NIR = f"{BODY}{97 - int(BODY) % 97:02d}"
NIR_SPACED = f"{NIR[0]} {NIR[1:3]} {NIR[3:5]} {NIR[5:7]} {NIR[7:10]} {NIR[10:13]} {NIR[13:]}"


@pytest.mark.parametrize("text, expected, kind", [
    ("Écrivez-moi à jean.dupont@example.com pour la réponse.", "Écrivez-moi à [e-mail] pour la réponse.", "email"),
    ("Mon numéro est le 06 12 34 56 78, merci.", "Mon numéro est le [téléphone], merci.", "phone"),
    ("Appelez le 0612345678.", "Appelez le [téléphone].", "phone"),
    ("Appelez le 06.12.34.56.78.", "Appelez le [téléphone].", "phone"),
    ("Appelez le +33 6 12 34 56 78.", "Appelez le [téléphone].", "phone"),
    ("Joignable au +44 7700 900123.", "Joignable au [téléphone].", "phone"),
    ("Mon IBAN : FR14 2004 1010 0505 0001 3M02 606.", "Mon IBAN : [IBAN].", "iban"),
    ("Ma carte 4111 1111 1111 1111 a expiré.", "Ma carte [carte bancaire] a expiré.", "card"),
    ("Ma carte 4111-1111-1111-1111 a expiré.", "Ma carte [carte bancaire] a expiré.", "card"),
    ("Ma carte 4111111111111111 a expiré.", "Ma carte [carte bancaire] a expiré.", "card"),
    ("Ma carte 3782 822463 10005 a expiré.", "Ma carte [carte bancaire] a expiré.", "card"),  # 4-6-5 layout
    (f"Mon numéro de sécu est {NIR_SPACED}.", "Mon numéro de sécu est [numéro de sécurité sociale].", "nir"),
    (f"Mon numéro de sécu est {NIR}.", "Mon numéro de sécu est [numéro de sécurité sociale].", "nir"),
])
def test_each_kind_of_identifier_is_masked(text, expected, kind):
    masked = pii.mask(text)
    assert masked.text == expected and masked.kinds == [kind]


@pytest.mark.parametrize("text, kind", [
    ("Mon n° : 2-85-05-75-123-456-23".replace("23", f"{97 - int('2850575123456') % 97:02d}"), "nir"),  # dashes, with its key
    ("Mon n° : 1 85 05 78 006 084", "nir"),  # the 13 digits people type, without the key
    ("Mon n° : 1.85.05.78.006.084", "nir"), ("Mon n° : 1850578006084", "nir"), ("Mon n° : 2A: 295062A123456", "nir"),
    ("carte 4532.0151.1283.0366", "card"), ("carte 4111  1111  1111  1111", "card"), ("carte 4111.1111.1111.1111", "card"),
    ("IBAN FR14-2004-1010-0505-0001-3M02-606", "iban"), ("IBAN FR14.2004.1010.0505.0001.3M02.606", "iban"),
    ("Tél +33 (0)6 12 34 56 78", "phone"), ("Tél (0)6 12 34 56 78", "phone"), ("Tél 06/12/34/56/78", "phone"),
    ("Tel +1 (415) 555-0132", "phone"), ("Tel +44 7700 900123", "phone"), ("Tel +32 470 12 34 56", "phone"),
    ("contact jean @ example.com", "email"), ("contact jean@example.co.uk", "email"), ("contact jean@münchen.de", "email"),
    ("né le 14/05/1985", "birth"), ("née le 14 mai 1985", "birth"), ("Date de naissance : 14 mai 1985", "birth"),
    ("born 1985-05-14", "birth"), ("nee 3 mars 1990", "birth"), ("DOB: 14.05.1985", "birth"),
])
def test_more_of_the_forms_people_really_type_are_found(text, kind):
    masked = pii.mask(text)
    assert kind in masked.kinds, (text, masked)


@pytest.mark.parametrize("text", [
    "tarif @ 5.50 euros", "Le prix est de 5 @ 10.5", "né 3 enfants", "ne le 3 mars 2025 pas plus", "il est né en 1985", "date de naissance du bébé",
    "né le", "le 14/05/1985 est un mardi", "durée du 14/05/1985 au 14/05/1986", "en 2023.2024.2025.2026", "3,5 % du 1 850 578",
    "+33", "+33 6", "(0)6", "+1 (415)", "+999 1", "avant le 14.05.1985",
])
def test_text_close_to_those_forms_is_still_left_alone(text):
    assert pii.mask(text).kinds == [], text


def test_several_identifiers_in_one_question_are_all_masked_and_counted():
    masked = pii.mask("Contact : a@b.fr ou 06 12 34 56 78, IBAN FR14 2004 1010 0505 0001 3M02 606.")
    assert masked.text == "Contact : [e-mail] ou [téléphone], IBAN [IBAN]." and sorted(masked.kinds) == ["email", "iban", "phone"]


@pytest.mark.parametrize("text", [
    "Que dit l'article L1221-13 du Code du travail ?",
    "Quelle est la règle de l'article R*3231-4 ?",
    "Que dit la loi n° 2008-596 du 25 juin 2008 ?",
    "Le décret 2017-1387 change-t-il le plafond ?",
    "Le service interroge 11 705 textes de loi.",
    "Quelle est la durée légale : 35 heures par semaine ?",
    "Je suis en CDI depuis le 01/02/2024, avec un salaire de 2 500 euros et un préavis de 15 jours.",
    "Une indemnité de 20 000 euros est-elle possible pour 12 salariés ?",
    "Que dit l'article 17 du RGPD ? Et le considérant 47 ?",
    "FR76 1234 5678 9012 3456 7890 123",  # looks like an IBAN but its key is wrong
    "1234 5678 9012 3456",  # looks like a card number but fails the Luhn sum
    "Heptane-2-one 203-767-1 110-43-0 238 50 - 475 100 - Peau (7) - Phosgène 200-870-3 75-44-5 0,08 0,02 - 0,4 0,1",  # a table of the code
    "Le 1851378006080 est un nombre à 13 chiffres.",  # month 13: not a social security number
    "Le 1850500006080 est un nombre à 13 chiffres.",  # department 00
    "Le 1859678006080 est un nombre à 13 chiffres.",  # department 96 does not exist
    "tranches : 249 10 22 220 250 à 299 11 22 242 300 à 399 11 22 242 400",  # a table of the code: irregular groups
    "1 85 05.78 006 084 36",  # separators mixed: not a way anyone writes it
])
def test_numbers_of_the_law_and_ordinary_figures_are_left_alone(text):
    masked = pii.mask(text)
    assert masked.text == text and masked.kinds == []


def test_the_checks_themselves():
    assert pii.iban_ok("FR14 2004 1010 0505 0001 3M02 606") and not pii.iban_ok("FR14 2004 1010 0505 0001 3M02 607")
    assert pii.luhn_ok("4111 1111 1111 1111") and not pii.luhn_ok("4111 1111 1111 1112")
    assert pii.nir_ok(NIR) and not pii.nir_ok(f"{BODY}00")
    corsica = "295062A123456"  # department 2A: the letters count as 19 in the key
    assert pii.nir_ok(f"{corsica}{97 - int(corsica.replace('2A', '19')) % 97:02d}")

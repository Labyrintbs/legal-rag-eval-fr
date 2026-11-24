"""Masks structured personal identifiers in a visitor's question (step 0f, part 4): e-mail addresses, telephone numbers,
IBANs, bank card numbers and French social security numbers. It is a local program with no model, so nothing is sent
anywhere to find them. It does not find names or postal addresses: the privacy page says so.

A candidate is masked only when it passes the check of its own kind (the IBAN key, the Luhn sum of a card, the key of a
social security number), so that numbers of the law ("L1221-13", "loi 2008-596") and ordinary figures are left alone.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from functools import partial

SEP = r"[ .-]"  # what people put between groups of digits
# an e-mail address, with at most one space on each side of the "@" ("jean @ example.com"); the last label has letters, so
# "tarif @ 5.50" is not one
EMAIL = re.compile(r"[\w.+-]+(?: ?@ ?)[\w-]+(?:\.[\w-]+)*\.[^\W\d_]{2,}")
IBAN = re.compile(rf"(?<![A-Za-z0-9])[A-Z]{{2}}\d{{2}}(?:{SEP}?[A-Z0-9]{{4}}){{2,7}}(?:{SEP}?[A-Z0-9]{{1,4}})?(?![A-Za-z0-9])", re.IGNORECASE)
# a French social security number: 13 digits (sex, year, month, department, commune, order), with a 2-digit key or not
NIR = re.compile(rf"(?<!\d)[12]{SEP}?\d{{2}}{SEP}?(?:0[1-9]|1[0-2]|[2-9]\d){SEP}?(?:\d{{2}}|2[AB]){SEP}?\d{{3}}{SEP}?\d{{3}}(?:{SEP}?\d{{2}})?(?!\d)")
# a card as it is written: 13 to 19 digits in one block, groups of four (the last one may be shorter), or the 4-6-5 layout
CARD = re.compile(rf"(?<!\d)(?:\d{{13,19}}|\d{{4}}(?:{SEP}{{1,2}}\d{{4}}){{2,3}}(?:{SEP}{{1,2}}\d{{1,3}})?|\d{{4}}{SEP}{{1,2}}\d{{6}}{SEP}{{1,2}}\d{{5}})(?!\d)")
# a French number (0 + 9 digits, +33, 0033, "+33 (0)6"), or an international one with a "+"
PHONE = re.compile(rf"(?<![\d+])(?:(?:\+|00)33{SEP}?(?:\(0\){SEP}?)?|0|\(0\){SEP}?)[1-9](?:[ ./-]?\d{{2}}){{4}}(?!\d)"
                   rf"|(?<![\d+])\+(?!33)\d{{1,3}}{SEP}?(?:\(\d{{1,4}}\){SEP}?|\d{{1,4}}{SEP})?(?:{SEP}?\d){{5,11}}(?!\d)")
NIR_BLOCK = re.compile(r"[12]\d{4}(?:\d{2}|2[AB])\d{6}(?:\d{2})?")
NIR_GROUPS = re.compile(r"[12]([ .-])\d{2}\1\d{2}\1(?:\d{2}|2[AB])\1\d{3}\1\d{3}(?:\1\d{2})?")
MONTHS = "janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre"
# a date of birth, only when a word says so ("né le 14/05/1985", "date de naissance : 14 mai 1985", "born 1985-05-14")
BIRTH = re.compile(rf"(?:\bn(?:é|ée|ee)\b(?: le)?|date de naissance(?: ?:)?|\bborn\b(?: on)?|\bd\.?o\.?b\b ?:?) ?"
                   rf"(?:\d{{1,2}}[/.-]\d{{1,2}}[/.-]\d{{2,4}}|\d{{1,2}}(?:er)? (?:{MONTHS}) \d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})", re.IGNORECASE)

LABELS = {"email": "[e-mail]", "birth": "[date de naissance]", "iban": "[IBAN]", "nir": "[numéro de sécurité sociale]",
          "card": "[carte bancaire]", "phone": "[téléphone]"}


@dataclass
class Masked:
    text: str
    kinds: list[str] = field(default_factory=list)  # one entry for each identifier masked; empty: nothing changed


def iban_ok(candidate: str) -> bool:
    """The check of an IBAN: move the first four characters to the end, letters become 10 to 35, the number mod 97 is 1."""
    flat = re.sub(r"[ .-]", "", candidate)
    if not 15 <= len(flat) <= 34:
        return False
    moved = flat[4:] + flat[:4]
    return int("".join(str(int(c, 36)) for c in moved)) % 97 == 1


def luhn_ok(candidate: str) -> bool:
    digits = [int(c) for c in re.sub(r"\D", "", candidate)]
    if not 13 <= len(digits) <= 19:
        return False
    total = sum(d if i % 2 == 0 else (d * 2 - 9 if d * 2 > 9 else d * 2) for i, d in enumerate(reversed(digits)))
    return total % 10 == 0


def card_ok(candidate: str) -> bool:
    """The Luhn sum, except for a run of years ("2023 2024 2025 2026"), which passes it now and then by chance."""
    digits = re.sub(r"\D", "", candidate)
    years = len(digits) % 4 == 0 and all(1900 <= int(digits[i:i + 4]) <= 2100 for i in range(0, len(digits), 4))
    return luhn_ok(candidate) and not years


def nir_ok(candidate: str) -> bool:
    """A social security number. With its key (15 characters), the last two digits must be 97 minus the rest mod 97 (Corsica:
    2A and 2B count as 19 and 18). Without it (13 characters, the form people type most), the month must be 01 to 12 and
    the department a real one (01 to 95, 2A, 2B, 97 to 99): that is the shape alone, so it is the stricter of the two."""
    if not (NIR_BLOCK.fullmatch(candidate.upper()) or NIR_GROUPS.fullmatch(candidate.upper())):
        return False  # a number is written in one block or in the standard groups with one separator: a table of figures is not
    flat = re.sub(r"[ .-]", "", candidate).upper()
    if len(flat) not in (13, 15):
        return False
    body = flat[:13]
    department = body[5:7]
    if not (1 <= int(body[3:5]) <= 12 and (department in ("2A", "2B") or 1 <= int(department) <= 95 or department in ("97", "98", "99"))):
        return len(flat) == 15 and nir_key_ok(flat)  # month 20 and more (a foreigner born abroad): only with a valid key
    return len(flat) == 13 or nir_key_ok(flat)


def nir_key_ok(flat: str) -> bool:
    body = flat[:13].replace("2A", "19").replace("2B", "18")
    return body.isdigit() and 97 - int(body) % 97 == int(flat[13:])


CHECKS = (("email", EMAIL, None), ("birth", BIRTH, None), ("iban", IBAN, iban_ok), ("nir", NIR, nir_ok), ("card", CARD, card_ok),
          ("phone", PHONE, None))


def replace_if_valid(match: re.Match, kind: str, check, found: list[str]) -> str:
    """The label of `kind` when the candidate passes its own check, the candidate itself otherwise."""
    if check and not check(match.group()):
        return match.group()
    found.append(kind)
    return LABELS[kind]


def normalise(text: str) -> str:
    """The text as the filter reads it: compatibility forms folded (fullwidth digits and "＠" become plain ones, a decomposed
    "é" is composed) and invisible format characters (zero-width spaces and the like) removed, so that they cannot hide an
    identifier. The masked text keeps this form."""
    folded = unicodedata.normalize("NFKC", text)
    return "".join(c for c in folded if unicodedata.category(c) != "Cf")


def mask(text: str) -> Masked:
    """The text with each identifier replaced by a label such as "[e-mail]". The kinds are tried in the order of CHECKS,
    and a label holds no digit, so a later kind never sees what an earlier one masked."""
    text = normalise(text)
    found: list[str] = []
    for kind, pattern, check in CHECKS:
        text = pattern.sub(partial(replace_if_valid, kind=kind, check=check, found=found), text)
    return Masked(text, found)

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

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
IBAN = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?(?![A-Za-z0-9])", re.IGNORECASE)
NIR = re.compile(r"(?<!\d)[12][ .]?\d{2}[ .]?(?:0[1-9]|1[0-2]|[2-9]\d)[ .]?(?:\d{2}|2[AB])[ .]?\d{3}[ .]?\d{3}[ .]?\d{2}(?!\d)")
# a card as it is written: 13 to 19 digits in one block, groups of four (the last one may be shorter), or the 4-6-5 layout
CARD = re.compile(r"(?<!\d)(?:\d{13,19}|\d{4}(?:[ -]\d{4}){2,3}(?:[ -]\d{1,3})?|\d{4}[ -]\d{6}[ -]\d{5})(?!\d)")
PHONE = re.compile(r"(?<![\d+])(?:(?:\+|00)33[ .-]?|0)[1-9](?:[ .-]?\d{2}){4}(?!\d)|(?<![\d+])\+(?!33)\d{1,3}(?:[ .-]?\d){8,12}(?!\d)")

LABELS = {"email": "[e-mail]", "iban": "[IBAN]", "nir": "[numéro de sécurité sociale]", "card": "[carte bancaire]",
          "phone": "[téléphone]"}


@dataclass
class Masked:
    text: str
    kinds: list[str] = field(default_factory=list)  # one entry for each identifier masked; empty: nothing changed


def iban_ok(candidate: str) -> bool:
    """The check of an IBAN: move the first four characters to the end, letters become 10 to 35, the number mod 97 is 1."""
    flat = candidate.replace(" ", "")
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


def nir_ok(candidate: str) -> bool:
    """A 15-character social security number: the last two digits are 97 minus the rest mod 97 (Corsica: 2A and 2B count as 19 and 18)."""
    flat = re.sub(r"[ .]", "", candidate)
    if len(flat) != 15:
        return False
    body = flat[:13].replace("2A", "19").replace("2B", "18")
    return body.isdigit() and 97 - int(body) % 97 == int(flat[13:])


CHECKS = (("email", EMAIL, None), ("iban", IBAN, iban_ok), ("nir", NIR, nir_ok), ("card", CARD, luhn_ok), ("phone", PHONE, None))


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

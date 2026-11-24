"""Measures the personal-data filter `answering/pii.py` (step 0f, part 4), on real text and on invented personal data.
False positives: how many questions and passages of the law the filter changes although they hold no personal data
(the target is zero). Recall: how many invented identifiers in sentences it masks. Names and postal addresses are not
in its scope: a few are listed to show that they pass. No model call, no cost.
  uv run python scripts/answers/pii_check.py
"""

import json
import random
from collections import Counter
from pathlib import Path

from legalrag.answering import pii
from legalrag.index import db

ROOT = Path(__file__).parents[2]
SEED = 20261124


def gold_questions() -> list[str]:
    return [json.loads(line)["question"] for line in (ROOT / "eval/gold.jsonl").read_text().splitlines() if line.strip()]


def heading_sentences() -> list[str]:
    out = []
    for path in sorted((ROOT / "data/pilot").glob("heading_deepseek-flash-v3*.jsonl")):
        out += [json.loads(line)["sentence"] for line in path.read_text().splitlines() if '"sentence"' in line]
    return out


def passages() -> list[str]:
    with db.connect() as conn:
        return [row[0] for row in conn.execute("SELECT body_text FROM chunks")]


def false_positives(name: str, texts: list[str]) -> None:
    changed = [(t, pii.mask(t)) for t in texts]
    changed = [(t, m) for t, m in changed if m.kinds]
    print(f"{name}: {len(changed)} of {len(texts)} changed")
    for text, masked in changed[:8]:
        where = pii.CHECKS and [m for m in masked.kinds]
        print(f"   {where}  {text[:110]!r}")


def digits(rng: random.Random, n: int) -> str:
    return "".join(str(rng.randrange(10)) for _ in range(n))


def luhn_number(rng: random.Random) -> str:
    body = digits(rng, 15)
    total = sum(d if i % 2 == 1 else (d * 2 - 9 if d * 2 > 9 else d * 2) for i, d in enumerate(int(c) for c in reversed(body)))
    return body + str((10 - total % 10) % 10)


def iban(rng: random.Random) -> str:
    bban = digits(rng, 23)
    check = 98 - int(bban + "152700", 10) % 97  # F=15, R=27, then "00"
    return f"FR{check:02d}{bban}"


def nir(rng: random.Random) -> str:
    body = f"{rng.choice('12')}{digits(rng, 2)}{rng.randrange(1, 13):02d}{rng.randrange(1, 96):02d}{digits(rng, 6)}"
    return f"{body}{97 - int(body) % 97:02d}"


def grouped(text: str, sizes: list[int], sep: str) -> str:
    out, start = [], 0
    for size in sizes:
        out.append(text[start:start + size])
        start += size
    return sep.join(out)


def invented(rng: random.Random) -> dict[str, list[str]]:
    emails = [f"{rng.choice(['jean.dupont', 'marie_martin', 'p.durand', 'contact+rh'])}{rng.randrange(100)}@{rng.choice(['example.com', 'mail.fr', 'entreprise.co.uk', 'gmail.com'])}" for _ in range(30)]
    phones = []
    for _ in range(40):
        number = f"0{rng.randrange(1, 10)}{digits(rng, 8)}"
        phones.append(rng.choice([number, grouped(number, [2] * 5, " "), grouped(number, [2] * 5, "."), grouped(number, [2] * 5, "-"),
                                  "+33 " + grouped(number[1:], [1, 2, 2, 2, 2], " "), "+33" + number[1:], "0033" + number[1:]]))
    ibans = [rng.choice([(i := iban(rng)), grouped(i, [4] * 6 + [3], " ")]) for _ in range(30)]
    cards = [rng.choice([(c := luhn_number(rng)), grouped(c, [4] * 4, " "), grouped(c, [4] * 4, "-")]) for _ in range(30)]
    nirs = [rng.choice([(n := nir(rng)), grouped(n, [1, 2, 2, 2, 3, 3, 2], " "), grouped(n, [1, 2, 2, 2, 3, 3, 2], ".")]) for _ in range(30)]
    return {"email": emails, "phone": phones, "iban": ibans, "card": cards, "nir": nirs}


TEMPLATES = ["Mon salarié, joignable au {} , a démissionné : quel préavis ?", "Voici mes coordonnées : {}. Quelle est la durée du préavis ?",
             "{} — peut-on me licencier pendant un arrêt maladie ?"]
NOT_IN_SCOPE = ["Mon collègue Pierre Martin a été licencié : a-t-il droit à une indemnité ?", "J'habite 12 rue de la Paix, 75002 Paris : mon employeur peut-il me muter ?",
                "Je suis né le 3 mars 1985 : quelle est ma durée de préavis ?", "Madame Sophie Leroy, directrice des ressources humaines, refuse mon congé."]


def recall(rng: random.Random) -> None:
    for kind, values in invented(rng).items():
        masked = [pii.mask(rng.choice(TEMPLATES).format(v)) for v in values]
        hit = sum(kind in m.kinds for m in masked)
        wrong_kind = Counter(k for m in masked for k in m.kinds if k != kind)
        print(f"{kind:>6}: {hit} of {len(values)} masked as {kind}" + (f"; also masked as {dict(wrong_kind)}" if wrong_kind else ""))
        for v, m in zip(values, masked, strict=True):
            if kind not in m.kinds:
                print(f"         missed: {v!r}")
    print("not in scope (names, addresses, birth date), masked or not:")
    for text in NOT_IN_SCOPE:
        print(f"   {'masked' if pii.mask(text).kinds else 'passes'}  {text}")


def main() -> None:
    false_positives("gold questions", gold_questions())
    false_positives("generated heading questions", heading_sentences())
    false_positives("passages of the law", passages())
    recall(random.Random(SEED))


if __name__ == "__main__":
    main()

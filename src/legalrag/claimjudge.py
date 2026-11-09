"""The judge of claims (step 0d): given one claim and the passages it cites, a model says whether they back it.
Validated against the labels made by hand on the sheets of `labelsheet` before it scores anything else.
"""

from collections import Counter
from dataclasses import dataclass
from typing import Literal, get_args

from pydantic import BaseModel, field_validator

from legalrag import labelsheet

Label = Literal["supported", "partly", "not supported"]
LABELS = get_args(Label)


class Verdict(BaseModel):
    """The reply of the judge: the detail that decides, then the label."""

    reason: str = ""
    label: Label

    @field_validator("label", mode="before")
    @classmethod
    def lowercase(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


@dataclass(frozen=True)
class Item:
    key: str  # "<answer or check id>|claim<N>", as in the label files
    claim: str
    passages: list[tuple[str, str]]  # (article label, passage)
    human: str


def collect(labels: dict[str, str], rows: list[dict], checks: list[dict]) -> list[Item]:
    """The labelled claims with their text and cited passages. `rows`: the pilot answers (with the key "text");
    `checks`: the items of `labelsheet.load_checks`."""
    by_id = {r["id"]: r for r in rows}
    edited = {c["id"]: c["claim"] for c in checks}
    items = []
    for key, human in labels.items():
        name, _, what = key.partition("|")
        if not what.startswith("claim"):
            continue
        claim = edited[name] if name in edited else labelsheet.parse_answer(by_id[name]["text"])[int(what[len("claim"):])]
        items.append(Item(key, claim.text, claim.passages, human))
    return items


def messages(prompt: dict, item: Item) -> list[dict]:
    passages = "\n".join(f"[{label}] {text}" for label, text in item.passages)
    return [{"role": "system", "content": prompt["system"].strip()},
            {"role": "user", "content": prompt["user"].format(claim=item.claim, passages=passages)}]


def parse(text: str) -> tuple[str, str]:
    """(label, reason) of the judge's reply; a ValueError (pydantic's ValidationError) when it is not a verdict."""
    verdict = Verdict.model_validate_json(text)
    return verdict.label, verdict.reason


def kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Cohen's kappa of (human, judge) label pairs: agreement beyond what the label shares would give by chance."""
    n = len(pairs)
    if n == 0:
        return None
    observed = sum(a == b for a, b in pairs) / n
    humans, judges = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    chance = sum(humans[label] * judges[label] for label in LABELS) / n**2
    return None if chance == 1 else (observed - chance) / (1 - chance)


def confusion(pairs: list[tuple[str, str]]) -> dict[str, dict[str, int]]:
    """{human label: {judge label: count}}."""
    table = {a: {b: 0 for b in LABELS} for a in LABELS}
    for human, judge in pairs:
        table[human][judge] += 1
    return table


def report(pairs: list[tuple[str, str]]) -> dict:
    """Agreement, kappa, and the two rates that matter: errors the judge catches and good claims it flags."""
    errors = [(h, j) for h, j in pairs if h != "supported"]
    good = [(h, j) for h, j in pairs if h == "supported"]
    return {"n": len(pairs), "agreement": sum(h == j for h, j in pairs) / len(pairs) if pairs else None,
            "kappa": kappa(pairs), "errors": len(errors), "errors_caught": sum(j != "supported" for _, j in errors),
            "good": len(good), "good_flagged": sum(j != "supported" for _, j in good), "confusion": confusion(pairs)}

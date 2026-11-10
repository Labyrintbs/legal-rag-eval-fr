"""The judge of claims (step 0d): given one claim and the passages it cites, a model says whether they back it.
Validated against the labels made by hand on the sheets of `labelsheet` before it scores anything else.
"""

import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

import httpx
from pydantic import BaseModel, field_validator

from legalrag import llm
from legalrag.evaluation import labelsheet
from legalrag.evaluation import questiongen as qg

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


def run_judge(items: list[Item], model: str, think: bool, run_cap: float, workers: int, tag: str,
              prompt_id: str) -> list[dict]:
    """One call per item, no retry: {key, human, label, reason}, or {key, human, error} when the call or the reply
    failed. The calls are in the DeepSeek ledger under the label `judge-<tag>`."""
    prompt = qg.load_prompts(Path("prompts/judge.yaml"))["prompts"][prompt_id]
    budget = llm.Budget(run_cap=run_cap, total_cap=5.0)
    http = llm.make_http(os.environ["DEEPSEEK_API_KEY"])
    max_tokens = prompt["max_tokens_thinking"] if think else prompt["max_tokens"]
    with ThreadPoolExecutor(workers) as pool:
        futures = [pool.submit(judge_one, http, budget, f"judge-{tag}", model, think, max_tokens, messages(prompt, item), item)
                   for item in items]
        return [future.result() for future in futures]


def judge_one(http: httpx.Client, budget: llm.Budget, label: str, model: str, think: bool, max_tokens: int,
              chat: list[dict], item: Item) -> dict:
    row = {"key": item.key, "human": item.human}
    try:
        text = llm.chat(http, llm.LEDGER, budget, label, model, chat, max_tokens, thinking=think, json_mode=True,
                        temperature=None if think else 0)
        row["label"], row["reason"] = parse(text)
    except (httpx.HTTPError, ValueError, KeyError, llm.BudgetExceeded) as error:
        row["error"] = f"{type(error).__name__}: {error}"
    return row


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

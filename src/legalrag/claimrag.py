"""ClaimRAG-LAW, English GDPR part (step 0d): the expert-labelled claims, turned into sentences, as an outside check
of the claim judge. Each claim is a triple (subject, relation, object) that an expert labelled Entailment, Neutral or
Contradiction against the source chunk of its question. Data: https://huggingface.co/datasets/SNTSVV/ClaimRAG-LAW
(CC BY 4.0, research use), kept in data/claimrag/ and never committed.
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import httpx

from legalrag import claimjudge, llm
from legalrag import questiongen as qg

# the judge's labels are compared in two classes; claims the expert labelled otherwise are left out
BINARY = {"Entailment": "supported", "Neutral": "not supported", "Contradiction": "not supported"}


@dataclass(frozen=True)
class Triple:
    key: str  # "<query id>|<claim index>"
    parts: tuple[str, str, str]
    label: str  # the expert's entailment label
    chunk: str  # the source chunk of the question


def load_claims(path: Path) -> list[Triple]:
    """The claims of GDPR-CLAIM-LAW.json that have a label in `BINARY`."""
    data = json.loads(path.read_text())
    triples = []
    for item in data["input_data"] if isinstance(data, dict) else data:  # the claim file is a bare list
        for index, claim in enumerate(item["claims"]):
            if claim.get("claim_entailment") in BINARY and len(claim["claim"]) == 3:
                triples.append(Triple(f"{item['query_id']}|{index}", tuple(claim["claim"]), claim["claim_entailment"],
                                      item["relevant_chunk"]))
    return triples


def half(key: str) -> str:
    """"dev" or "test" for a claim key: by question (even or odd query id), so the claims of one question stay together."""
    return "dev" if int(key.split("|")[0]) % 2 == 0 else "test"


def template_sentence(parts: tuple[str, str, str]) -> str:
    """The three parts in a row, as a sentence: faithful to the claim, sometimes clumsy."""
    text = " ".join(p.strip() for p in parts)
    return text[:1].upper() + text[1:] + "."


def rewrite_one(http: httpx.Client, budget: llm.Budget, label: str, model: str, prompt: dict, triple: Triple) -> str | None:
    """One sentence for the triple by the model, or None when the call failed (a rerun tries it again)."""
    subject, relation, obj = triple.parts
    chat = [{"role": "system", "content": prompt["system"].strip()},
            {"role": "user", "content": prompt["user"].format(subject=subject, relation=relation, object=obj)}]
    try:
        return llm.chat(http, llm.LEDGER, budget, label, model, chat, prompt["max_tokens"], thinking=False, json_mode=False,
                        temperature=0).strip()
    except (httpx.HTTPError, ValueError, KeyError, llm.BudgetExceeded):
        return None


def rewrite_all(triples: list[Triple], model: str, run_cap: float, workers: int, tag: str) -> list[str | None]:
    prompt = qg.load_prompts(Path("prompts/claim_rewrite.yaml"))["prompts"]["claim.rewrite.v1"]
    budget = llm.Budget(run_cap=run_cap, total_cap=5.0)
    http = llm.make_http(os.environ["DEEPSEEK_API_KEY"])
    with ThreadPoolExecutor(workers) as pool:
        futures = [pool.submit(rewrite_one, http, budget, f"claim-rewrite-{tag}", model, prompt, t) for t in triples]
        return [future.result() for future in futures]


def to_items(triples: list[Triple], sentences: list[str | None]) -> list[claimjudge.Item]:
    """Judge items: the sentence as the claim, the source chunk as the only passage, the expert's label in two classes.
    Triples whose sentence is missing or whose chunk is empty (some are in the file) are left out."""
    return [claimjudge.Item(t.key, s, [("GDPR source chunk", t.chunk)], BINARY[t.label])
            for t, s in zip(triples, sentences, strict=True) if s and t.chunk.strip()]

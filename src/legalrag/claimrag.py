"""ClaimRAG-LAW, English GDPR part (step 0d): the expert-labelled claims, turned into sentences, as an outside check
of the claim judge. Each claim is a triple (subject, relation, object) that an expert labelled Entailment, Neutral or
Contradiction against the source chunk of its question. Data: https://huggingface.co/datasets/SNTSVV/ClaimRAG-LAW
(CC BY 4.0, research use), kept in data/claimrag/ and never committed.
"""

import json
import os
import random
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

import httpx

from legalrag import claimjudge, labelsheet, llm
from legalrag import questiongen as qg

# the judge's labels are compared in two classes; claims the expert labelled otherwise are left out
BINARY = {"Entailment": "supported", "Neutral": "not supported", "Contradiction": "not supported"}


@dataclass(frozen=True)
class Triple:
    key: str  # "<query id>|<claim index>"
    parts: tuple[str, str, str]
    label: str  # the expert's entailment label
    chunk: str  # the source chunk of the question, as the claim file gives it
    query: str = ""


def load_claims(path: Path) -> list[Triple]:
    """The claims of GDPR-CLAIM-LAW.json that have a label in `BINARY`."""
    data = json.loads(path.read_text())
    triples = []
    for item in data["input_data"] if isinstance(data, dict) else data:  # the claim file is a bare list
        for index, claim in enumerate(item["claims"]):
            if claim.get("claim_entailment") in BINARY and len(claim["claim"]) == 3:
                triples.append(Triple(f"{item['query_id']}|{index}", tuple(claim["claim"]), claim["claim_entailment"],
                                      item["relevant_chunk"], item["query"]))
    return triples


def with_rag_chunks(triples: list[Triple], rag_path: Path) -> list[Triple]:
    """The triples whose question is also in GDPR-RAG-LAW.json, with the chunk of that file, which is the longer one.
    Matched by the text of the question: the ids of the two files drift apart (id 31 of the claim file is id 30 of
    the RAG file)."""
    rag = {i["query"].strip(): i["relevant_chunk"] for i in json.loads(rag_path.read_text())["input_data"]}
    return [replace(t, chunk=rag[t.query.strip()]) for t in triples if t.query.strip() in rag]


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


GOLD_OVERLAP = 0.30  # tested on the 68 questions: the lists are the same from 0.30 to 0.50, noisy at 0.10
NGRAM = 5


@dataclass(frozen=True)
class Question:
    id: int
    text: str
    chunk: str  # the source text that answers it, cleaned
    kind: str  # "answerable" or "false_premise" (the dataset's own question category)
    reference_claims: list[str]  # the claims the expert labelled Entailment, as template sentences


def clean_chunk(text: str) -> str:
    """The source text without the markdown marks and separators the dataset adds; paragraphs stay on their own lines."""
    lines = [re.sub(r"[*#>]", "", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line and set(line) != {"-"})


def load_questions(claim_path: Path, rag_path: Path) -> list[Question]:
    """The questions of the claim file that have a source text: the longer text of the RAG file when the question is
    there (matched by its text), else the claim file's own. Questions with no source text are left out."""
    claims = json.loads(claim_path.read_text())
    rag = {i["query"].strip(): i for i in json.loads(rag_path.read_text())["input_data"]}
    questions = []
    for item in claims["input_data"] if isinstance(claims, dict) else claims:
        match = rag.get(item["query"].strip())
        chunk = clean_chunk(match["relevant_chunk"] if match else item["relevant_chunk"])
        if not chunk:
            continue
        references = [template_sentence(tuple(c["claim"])) for c in item["claims"]
                      if c.get("claim_entailment") == "Entailment" and len(c["claim"]) == 3]
        kind = "false_premise" if match and match.get("question_category") == "False Premise" else "answerable"
        questions.append(Question(item["query_id"], item["query"].strip(), chunk, kind, references))
    return questions


def _grams(text: str) -> set[tuple[str, ...]]:
    words = re.findall(r"\w+", re.sub(r"^article \d+\s*", "", text.strip().lower().replace("’", "'")))
    return {tuple(words[i:i + NGRAM]) for i in range(len(words) - NGRAM + 1)}


def gold_labels(chunk: str, articles: list[tuple[str, str]], threshold: float = GOLD_OVERLAP) -> list[str]:
    """The labels of our articles that count as right for a question: those that share at least `threshold` of the
    5-word sequences of the source text, or whose own sequences are at least `threshold` inside it. `articles` are
    (label, text) pairs."""
    chunk_grams = _grams(chunk)
    gold = []
    for label, text in articles:
        grams = _grams(text)
        shared = len(chunk_grams & grams)
        if chunk_grams and grams and (shared / len(chunk_grams) >= threshold or shared / len(grams) >= threshold):
            gold.append(label)
    return gold


def retrieval(rows: list[dict]) -> dict:
    """Hit@5 (a gold article among the top 5), recall@5 and the mean reciprocal rank of the first gold article, over the
    rows that have a gold list; and the hit rate per gold list (the questions on one article together)."""
    scored = [r for r in rows if r["gold"]]
    hits = [bool(set(r["top5"]) & set(r["gold"])) for r in scored]
    recalls = [len(set(r["top5"]) & set(r["gold"])) / len(set(r["gold"])) for r in scored]
    ranks = [next((i for i, label in enumerate(r["top5"], 1) if label in r["gold"]), None) for r in scored]
    per_gold: dict[str, list[bool]] = {}
    for r, hit in zip(scored, hits, strict=True):
        per_gold.setdefault(" + ".join(r["gold"]), []).append(hit)
    n = len(scored)
    return {"questions": n, "hit_at_5": sum(hits) / n if n else None, "recall_at_5": sum(recalls) / n if n else None,
            "mrr_at_5": sum(1 / rank for rank in ranks if rank) / n if n else None,
            "per_gold": {gold: [sum(hit), len(hit)] for gold, hit in per_gold.items()}}


def completeness_items(rows: list[dict]) -> list[claimjudge.Item]:
    """One item per reference claim of every answered row: the claim, with the answer's own claims as the passage."""
    items = []
    for row in rows:
        if row["outcome"] != "answered":
            continue
        answer = " ".join(c.text for c in labelsheet.parse_answer(row["text"]))
        items += [claimjudge.Item(f"{row['id']}|ref{i}", claim, [("answer", answer)], "")
                  for i, claim in enumerate(row["reference_claims"])]
    return items


def pick_pairs(items: list[claimjudge.Item], verdicts: list[dict], counts: dict[str, int], seed: int = 20261110) -> list[claimjudge.Item]:
    """A sample of completeness items for the hand check: `counts` of them per label of the judge, at most one per
    question while there are enough questions, shuffled so the sheet does not reveal the judge's label."""
    label = {v["key"]: v["label"] for v in verdicts if v.get("label")}
    rng = random.Random(seed)
    pool = [i for i in items if i.key in label]
    rng.shuffle(pool)
    chosen, used = [], set()
    for want, n in counts.items():
        for strict in (True, False):  # first one per question, then the rest
            for item in pool:
                if len([c for c in chosen if label[c.key] == want]) >= n:
                    break
                question = item.key.split("|")[0]
                if label[item.key] == want and item not in chosen and not (strict and question in used):
                    chosen.append(item)
                    used.add(question)
    rng.shuffle(chosen)
    return chosen


def completeness(rows: list[dict], verdicts: list[dict]) -> dict:
    """Share of the reference claims that the answers cover, over the answered questions that have reference claims;
    `covered` counts "supported" only, `covered_or_partly` adds "partly". Per-question shares are averaged too."""
    by_key = {v["key"]: v["label"] for v in verdicts if v.get("label")}
    per_question, total, covered, lenient = [], 0, 0, 0
    for row in rows:
        labels = [by_key[f"{row['id']}|ref{i}"] for i in range(len(row["reference_claims"])) if f"{row['id']}|ref{i}" in by_key]
        if row["outcome"] != "answered" or not labels:
            continue
        total += len(labels)
        covered += labels.count("supported")
        lenient += sum(x != "not supported" for x in labels)
        per_question.append(labels.count("supported") / len(labels))
    return {"questions": len(per_question), "reference_claims": total, "covered": covered, "covered_or_partly": lenient,
            "claim_recall": covered / total if total else None,
            "claim_recall_or_partly": lenient / total if total else None,
            "mean_per_question": sum(per_question) / len(per_question) if per_question else None}

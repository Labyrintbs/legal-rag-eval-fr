"""Reranker: a cross-encoder reads the question and one chunk together and gives a relevance score.
The candidates of the first search (dense) are re-ordered by it; an article scores as its best chunk.
"""

from typing import Protocol

import psycopg

from legalrag.smoke import article_label, split_label

DEFAULT_MODEL = "BAAI/bge-reranker-v2-m3"
# Tokens of question and chunk (and for Qwen the prompt) together. Sized so the longest default-run chunk fits
# with the longest gold question; pairs cut anyway are counted as truncated_pairs in the run record.
CROSS_ENCODER_MAX_LENGTH = 1152
QWEN_MAX_LENGTH = 1700
BATCH_SIZE = 16
CANDIDATE_TEXTS = (
    "SELECT a.source_code, a.kind, a.article_num, c.embed_text FROM chunks c "
    "JOIN articles a ON a.uid = c.article_uid WHERE c.run_id = %s AND c.lang = %s "
    "AND a.source_code || '|' || a.kind || '|' || a.article_num = ANY(%s)"
)


class Scorer(Protocol):
    def score(self, pairs: list[tuple[str, str]]) -> list[float]: ...


class CrossEncoderScorer:
    """A sentence-transformers cross-encoder. Imports torch lazily."""

    def __init__(self, model: str = DEFAULT_MODEL, device: str = "auto") -> None:
        import torch
        from huggingface_hub import model_info
        from sentence_transformers import CrossEncoder

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model_name, self.device = model, device
        self.revision = model_info(model).sha
        self.model = CrossEncoder(model, device=device, max_length=CROSS_ENCODER_MAX_LENGTH, revision=self.revision)
        self.truncated = 0

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        if not pairs:
            return []
        questions, chunks = zip(*pairs, strict=True)
        lengths = self.model.tokenizer(list(questions), list(chunks))["input_ids"]
        self.truncated += sum(len(ids) > CROSS_ENCODER_MAX_LENGTH for ids in lengths)
        return [float(s) for s in self.model.predict(pairs, batch_size=BATCH_SIZE, show_progress_bar=False)]

    def info(self) -> dict:
        return {"model": self.model_name, "model_revision": self.revision, "device": self.device,
                "max_length": CROSS_ENCODER_MAX_LENGTH, "truncated_pairs": self.truncated}


# Prompt of the Qwen3-Reranker model card (copied verbatim); the instruction is ours, fixed before any run.
QWEN_PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct "
    'provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
)
QWEN_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
QWEN_INSTRUCTION = "Given a French legal question, retrieve the article of the Code du travail or the GDPR that answers it"


def qwen_body(query: str, document: str) -> str:
    return f"<Instruct>: {QWEN_INSTRUCTION}\n<Query>: {query}\n<Document>: {document}"


def fit(token_ids: list[list[int]], room: int) -> tuple[list[list[int]], int]:
    """Every token list cut to `room` tokens, and how many lists were cut."""
    return [ids[:room] for ids in token_ids], sum(len(ids) > room for ids in token_ids)


class QwenScorer:
    """Qwen3-Reranker: a language model asked whether the document answers the query; the score is the
    probability of "yes" against "no" (needs transformers 4.51 or later). Imports torch lazily."""

    def __init__(self, model: str, device: str = "auto") -> None:
        import torch
        from huggingface_hub import model_info
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model_name, self.device = model, device
        self.revision = model_info(model).sha
        self.tokenizer = AutoTokenizer.from_pretrained(model, padding_side="left", revision=self.revision)
        self.model = AutoModelForCausalLM.from_pretrained(model, revision=self.revision).to(device).eval()
        self.yes = self.tokenizer.convert_tokens_to_ids("yes")
        self.no = self.tokenizer.convert_tokens_to_ids("no")
        self.prefix = self.tokenizer.encode(QWEN_PREFIX, add_special_tokens=False)
        self.suffix = self.tokenizer.encode(QWEN_SUFFIX, add_special_tokens=False)
        self.truncated = 0

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        import torch

        scores: list[float] = []
        room = QWEN_MAX_LENGTH - len(self.prefix) - len(self.suffix)
        for start in range(0, len(pairs), BATCH_SIZE):
            bodies = [qwen_body(q, d) for q, d in pairs[start:start + BATCH_SIZE]]
            ids, cut = fit(self.tokenizer(bodies, padding=False, return_attention_mask=False)["input_ids"], room)
            self.truncated += cut
            batch = self.tokenizer.pad({"input_ids": [self.prefix + i + self.suffix for i in ids]},
                                       padding=True, return_tensors="pt").to(self.device)
            with torch.no_grad():
                last = self.model(**batch).logits[:, -1, :]
            two = torch.stack([last[:, self.no], last[:, self.yes]], dim=1)
            scores += torch.log_softmax(two.float(), dim=1)[:, 1].exp().tolist()
        return scores

    def info(self) -> dict:
        return {"model": self.model_name, "model_revision": self.revision, "device": self.device,
                "max_length": QWEN_MAX_LENGTH, "truncated_pairs": self.truncated, "instruction": QWEN_INSTRUCTION}


def make_scorer(model: str, device: str = "auto") -> Scorer:
    """The Qwen3 rerankers are language models with their own prompt; the others are cross-encoders."""
    return QwenScorer(model, device) if model.startswith("Qwen/Qwen3-Reranker") else CrossEncoderScorer(model, device)


def chunk_texts(conn: psycopg.Connection, run_id: int, lang: str, labels: list[str]) -> dict[str, list[str]]:
    """Embedded text of every chunk of the given articles, by article label."""
    keys = ["|".join(split_label(label)) for label in labels]
    texts: dict[str, list[str]] = {}
    for source, kind, num, text in conn.execute(CANDIDATE_TEXTS, (run_id, lang, keys)).fetchall():
        texts.setdefault(article_label(source, kind, num), []).append(text)
    return texts


def rerank(
    conn: psycopg.Connection, run_id: int, lang: str, question: str, candidates: list[tuple[str, str]],
    scorer: Scorer, keep: int,
) -> list[tuple[str, str]]:
    """The candidates ordered by the best chunk score of each article; equal scores keep the first
    search's order."""
    texts = chunk_texts(conn, run_id, lang, [label for label, _ in candidates])
    pairs = [(question, text) for label, _ in candidates for text in texts.get(label, [])]
    scores = iter(scorer.score(pairs))
    best = {}
    for label, _ in candidates:
        best[label] = max((next(scores) for _ in texts.get(label, [])), default=float("-inf"))
    ordered = sorted(candidates, key=lambda candidate: -best[candidate[0]])
    return ordered[:keep]

"""bge-m3 sparse (lexical) weights (step 0c): the same model as the dense search gives one non-negative weight
per token, relu(linear(last hidden state)), from `sparse_linear.pt` in the model repository. A text keeps the
largest weight of each token id (special tokens dropped); a question and a chunk score the sum of weight
products over the tokens they share. Rules checked against the FlagEmbedding code, 2026-11-03.
"""

from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from legalrag.embed import MAX_SEQ_LENGTH, MODEL, embed_text_hash
from legalrag.models import Chunk

BATCH_SIZE = 16
DEFAULT_FILE = Path("data/embeddings/bge-m3-sparse-default.parquet")
CHUNKS_SEARCHED = 400


def pool(ids, weights, unused: set[int]) -> tuple[list[int], list[float]]:
    """(token ids ascending, weights): the largest positive weight of each token id, special tokens dropped."""
    best: dict[int, float] = {}
    for token, weight in zip(ids, weights, strict=True):
        token, weight = int(token), float(weight)
        if token not in unused and weight > 0 and weight > best.get(token, 0.0):
            best[token] = weight
    order = sorted(best)
    return order, [best[token] for token in order]


class SparseEncoder:
    """bge-m3 with its sparse head. Imports torch lazily. float16 on the GPU, float32 on the CPU."""

    def __init__(self, device: str = "auto", model: str = MODEL) -> None:
        import torch
        from huggingface_hub import hf_hub_download, model_info
        from transformers import AutoModel, AutoTokenizer

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model_name, self.device = model, device
        self.revision = model_info(model).sha
        dtype = torch.float16 if device == "cuda" else torch.float32
        self.tokenizer = AutoTokenizer.from_pretrained(model, revision=self.revision)
        self.model = AutoModel.from_pretrained(model, revision=self.revision, dtype=dtype).to(device).eval()
        self.linear = torch.nn.Linear(self.model.config.hidden_size, 1)
        state = torch.load(hf_hub_download(model, "sparse_linear.pt", revision=self.revision), map_location="cpu")
        self.linear.load_state_dict(state)
        self.linear = self.linear.to(device, dtype).eval()
        t = self.tokenizer
        self.unused = {t.cls_token_id, t.eos_token_id, t.pad_token_id, t.unk_token_id}

    def encode(self, texts: list[str], batch_size: int = BATCH_SIZE, max_length: int = MAX_SEQ_LENGTH,
               progress=None) -> list[tuple[list[int], list[float]]]:
        """One (token ids, weights) per text, in the order of the texts. Longest texts first, to waste less padding."""
        import torch

        order = sorted(range(len(texts)), key=lambda i: -len(texts[i]))
        out: list[tuple[list[int], list[float]] | None] = [None] * len(texts)
        for start in range(0, len(order), batch_size):
            chosen = order[start:start + batch_size]
            batch = self.tokenizer([texts[i] for i in chosen], padding=True, truncation=True, max_length=max_length,
                                   return_tensors="pt").to(self.device)
            with torch.no_grad():
                hidden = self.model(**batch).last_hidden_state
                weights = torch.relu(self.linear(hidden)).squeeze(-1).float().cpu().numpy()
            ids, mask = batch["input_ids"].cpu().numpy(), batch["attention_mask"].cpu().numpy().astype(bool)
            for row, i in enumerate(chosen):
                out[i] = pool(ids[row][mask[row]], weights[row][mask[row]], self.unused)
            if progress and (start // batch_size) % 50 == 0:
                progress(min(start + batch_size, len(order)), len(order))
        return out

    def info(self) -> dict:
        import torch

        peak = round(torch.cuda.max_memory_allocated() / 2**20) if self.device == "cuda" else None
        return {"model": self.model_name, "model_revision": self.revision, "device": self.device,
                "gpu": torch.cuda.get_device_name() if self.device == "cuda" else None, "peak_vram_mb": peak}


def write(path: Path, chunks: list[Chunk], encoded: list[tuple[list[int], list[float]]]) -> None:
    """One row per chunk: its key, the hash of the text that was encoded, and the sparse vector."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({
        "article_uid": [c.article_uid for c in chunks], "chunk_index": [c.chunk_index for c in chunks],
        "text_hash": [embed_text_hash(c.embed_text) for c in chunks],
        "token_ids": [np.asarray(ids, dtype=np.int32) for ids, _ in encoded],
        "weights": [np.asarray(w, dtype=np.float32) for _, w in encoded],
    }).to_parquet(path, index=False)


# the chunks of one run with the article each belongs to: (article uid, chunk index, lang, text,
# source, kind, article number, content hash)
RUN_CHUNKS = (
    "SELECT c.article_uid, c.chunk_index, c.lang, c.embed_text, a.source_code, a.kind, a.article_num, a.content_hash "
    "FROM chunks c JOIN articles a ON a.uid = c.article_uid WHERE c.run_id = %s"
)


class SparseIndex:
    """Exact inverted index over the sparse vectors, one per language: token id -> (chunk numbers, weights)."""

    def __init__(self, frame: pd.DataFrame, chunks) -> None:
        """frame: the parquet rows; chunks: RUN_CHUNKS rows. Stops if the two do not describe the same chunks."""
        stored = {(r.article_uid, r.chunk_index): r for r in frame.itertuples()}
        wanted = {(uid, index) for uid, index, *_ in chunks}
        if set(stored) != wanted:
            raise ValueError(f"sparse file and chunking run differ: {len(set(stored) ^ wanted)} chunks in only one of them")
        self.article: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
        postings: dict[str, dict[int, tuple[list[int], list[float]]]] = defaultdict(lambda: defaultdict(lambda: ([], [])))
        for uid, index, lang, text, source, kind, num, body_hash in chunks:
            row = stored[(uid, index)]
            if row.text_hash != embed_text_hash(text):
                raise ValueError(f"sparse vector of {uid} #{index} was made from another text than the chunk")
            number = len(self.article[lang])
            self.article[lang].append((source, kind, num, body_hash))
            for token, weight in zip(row.token_ids, row.weights, strict=True):
                ids, weights = postings[lang][int(token)]
                ids.append(number)
                weights.append(float(weight))
        self.postings = {
            lang: {t: (np.asarray(i, dtype=np.int32), np.asarray(w, dtype=np.float32)) for t, (i, w) in tokens.items()}
            for lang, tokens in postings.items()
        }

    def scores(self, query: tuple[list[int], list[float]], lang: str) -> np.ndarray:
        """Sum of query weight times chunk weight over the shared tokens, for every chunk of the language."""
        result = np.zeros(len(self.article[lang]), dtype=np.float32)
        for token, weight in zip(*query, strict=True):
            hit = self.postings[lang].get(int(token))
            if hit is not None:
                result[hit[0]] += weight * hit[1]
        return result

    def search(self, query: tuple[list[int], list[float]], lang: str, top: int = CHUNKS_SEARCHED) -> list[tuple[str, str, str, str]]:
        """(source, kind, article number, content hash) of the best chunks, best first; chunks sharing no token
        with the question are not returned."""
        scores = self.scores(query, lang)
        best = np.argsort(-scores, kind="stable")[:top]
        return [self.article[lang][i] for i in best if scores[i] > 0]

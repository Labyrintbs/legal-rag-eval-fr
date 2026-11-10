"""LLM-written heading sentence (step 0c): one plain sentence per article, from the article text only.
This module builds the prompt, draws the pilot sample and checks an answer; the calls are in
scripts/heading_sentence_pilot.py.
"""

import json
import random
import time

import httpx

from legalrag.answering import articlenum
from legalrag.corpus.ingest import header_inputs
from legalrag.corpus.models import Article
from legalrag.corpus.text import context_of

CONTEXT_LEVELS = 3
# Pilot sample: how many articles of each kind, drawn with a fixed seed from the sorted uids.
SAMPLE_PLAN = (("code_travail", "article", 40), ("rgpd", "article", 4), ("rgpd", "recital", 4), ("code_travail", "annex", 2))


SAMPLE_PLAN_EN = (("rgpd", "article", 6), ("rgpd", "recital", 6))
# A sentence with one of these flags is not put in a heading.
UNUSABLE = {"empty", "article_number"}
PROMPT_BY_LANG = {"fr": "sentence.v3", "en": "sentence.v3.en"}


def sample(articles: list[Article], seed: int, plan=SAMPLE_PLAN, lang: str = "fr") -> list[Article]:
    """The same articles for every backend: a seeded draw per (source, kind) from the uid-sorted pool."""
    rng = random.Random(seed)
    drawn = []
    for source, kind, count in plan:
        pool = sorted((a for a in articles if a.source_code == source and a.kind == kind and a.lang == lang),
                      key=lambda a: a.uid)
        drawn += rng.sample(pool, count)
    return drawn


def messages(prompt: dict, article: Article) -> list[dict]:
    """The model sees the document name, the last section titles and the (cut) body; never the article number."""
    doc = header_inputs(article)[0]
    context = context_of(article.section_path, CONTEXT_LEVELS) or prompt.get("no_context", "(non indiqué)")
    body = article.body_text[: prompt["max_body_chars"]]
    return [{"role": "system", "content": prompt["system"].strip()},
            {"role": "user", "content": prompt["user"].format(doc=doc, context=context, body=body).strip()}]


def clean(answer: str, max_words: int) -> tuple[str, list[str]]:
    """(sentence, flags): the first non-empty line without quotes, and what is wrong with it, if anything."""
    lines = [line.strip() for line in answer.strip().splitlines() if line.strip()]
    sentence = lines[0].strip(" \"'«»") if lines else ""
    flags = []
    if not sentence:
        flags.append("empty")
    if len(lines) > 1:
        flags.append("several_lines")
    if len(sentence.split()) > max_words:
        flags.append("too_long")
    if articlenum.mentions_article(sentence):
        flags.append("article_number")
    return sentence, flags


def ask_local(http: httpx.Client, model: str, chat: list[dict], max_tokens: int) -> dict:
    """One call to an OpenAI-compatible server (llama-server). Thinking is switched off through the chat
    template; a server that does not know the field ignores it. Returns text, seconds, usage and timings."""
    started = time.monotonic()
    response = http.post("/v1/chat/completions", json={
        "model": model, "messages": chat, "max_tokens": max_tokens, "temperature": 0, "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    })
    response.raise_for_status()
    data = response.json()
    return {"text": data["choices"][0]["message"].get("content") or "", "seconds": round(time.monotonic() - started, 3),
            "usage": data.get("usage"), "timings": data.get("timings")}


def load_sentences(path) -> dict[str, str]:
    """article uid -> sentence, from a file written by scripts/heading_sentences_all.py; sentences with an
    unusable flag are left out, so those articles keep the plain heading."""
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {r["uid"]: r["sentence"] for r in rows if r.get("type") != "run" and r.get("sentence")
            and not UNUSABLE & set(r["flags"])}

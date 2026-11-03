"""The answer path in plain code (step 0d): the numbered context shown to the model, the structure it answers
with, and the check of what it cites. A passage shown to the reader is always the stored text of the cited
units; ids that do not exist are dropped, and an answer left without a valid citation is a refusal.
"""

import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

from legalrag import trace
from legalrag.search import Hit
from legalrag.units import Unit, passage, split_units

ID = re.compile(r"(\d+)\.(\d+)")  # "2.3", "[2.3]" or "Source 2.3": source 2, unit 3


class Claim(BaseModel):
    text: str
    sources: list[str] = Field(default_factory=list)


class ModelAnswer(BaseModel):
    """What the model returns: a refusal, or claims that each cite the ids of the units that support them."""

    refusal: bool = False
    reason: str | None = None
    claims: list[Claim] = Field(default_factory=list)


@dataclass(frozen=True)
class Source:
    number: int  # 1-based, as in the prompt
    hit: Hit
    units: list[Unit]


@dataclass(frozen=True)
class Citation:
    source: int
    label: str
    chunk_index: int
    units: list[int]
    passage: str  # stored text of the cited units, with the lead-in of a list item
    section_path: str
    url: str


@dataclass
class Resolved:
    outcome: str  # answered, refused_by_model or invalid_citation (the values of trace.OUTCOMES)
    claims: list[tuple[str, list[Citation]]]
    reason: str | None = None
    dropped_ids: tuple[str, ...] = ()
    dropped_claims: int = 0


def make_sources(hits: list[Hit]) -> list[Source]:
    return [Source(i, hit, split_units(hit.text)) for i, hit in enumerate(hits, 1)]


def context(sources: list[Source]) -> str:
    """The text of the sources for the prompt: a title per source, then one line per unit with its id."""
    lines = []
    for s in sources:
        lines.append(f"[Source {s.number}] {s.hit.header or s.hit.label}")
        lines += [f"[{s.number}.{n}] " + " ".join(s.hit.text[u.start:u.end].split()) for n, u in enumerate(s.units, 1)]
        lines.append("")
    return "\n".join(lines).strip()


def parse_id(raw: str) -> tuple[int, int] | None:
    m = ID.search(raw)
    return (int(m.group(1)), int(m.group(2))) if m else None


def resolve(answer: ModelAnswer, sources: list[Source]) -> Resolved:
    """Turn the model's answer into claims with their passages. A claim keeps only the ids that exist and is dropped
    if none is left; no claim left is `invalid_citation` when the model gave claims, `refused_by_model` otherwise."""
    if answer.refusal:
        return Resolved("refused_by_model", [], answer.reason)
    by_number = {s.number: s for s in sources}
    claims, bad, dropped = [], [], 0
    for claim in answer.claims:
        cited: dict[int, list[int]] = {}
        for raw in claim.sources:
            parsed = parse_id(raw)
            if parsed and parsed[0] in by_number and 1 <= parsed[1] <= len(by_number[parsed[0]].units):
                cited.setdefault(parsed[0], []).append(parsed[1])
            else:
                bad.append(raw)
        if not cited:
            dropped += 1
            continue
        citations = [Citation(k, by_number[k].hit.label, by_number[k].hit.chunk_index, sorted(set(ns)),
                              passage(by_number[k].hit.text, by_number[k].units, ns), by_number[k].hit.section_path,
                              by_number[k].hit.url) for k, ns in cited.items()]
        claims.append((claim.text, citations))
    if claims:
        return Resolved("answered", claims, None, tuple(bad), dropped)
    if answer.claims:
        return Resolved("invalid_citation", [], "no claim with a valid citation", tuple(bad), dropped)
    return Resolved("refused_by_model", [], answer.reason or "no claim")


def render(resolved: Resolved) -> str:
    """Plain text of an answer: the claims with numbered marks, then the cited passages."""
    if resolved.outcome != "answered":
        return f"(no answer: {resolved.reason or resolved.outcome})"
    notes, lines = [], []
    for text, citations in resolved.claims:
        marks = []
        for c in citations:
            notes.append(f"[{len(notes) + 1}] {c.label} - {c.passage}")
            marks.append(f"[{len(notes)}]")
        lines.append(f"{text} {''.join(marks)}")
    return "\n".join(lines) + "\n\n" + "\n".join(notes)


@dataclass
class Result:
    """Everything one request produced, for the reader, the trace and the pilot."""

    outcome: str  # a value of trace.OUTCOMES
    text: str  # what the reader sees
    hits: list[Hit]
    resolved: Resolved | None = None
    reason: str | None = None
    error: str | None = None
    raw: str | None = None  # the model's reply, for debugging pilots; not stored in traces
    tokens_in: int | None = None
    tokens_out: int | None = None
    tokens_cached: int | None = None
    cost_usd: float | None = None
    retrieval_ms: int | None = None
    llm_ms: int | None = None
    total_ms: int | None = None


def usage_of(usage) -> tuple[int | None, int | None, int | None]:
    """(tokens in, tokens out, cached tokens) from the usage block of a DeepSeek reply."""
    if usage is None:
        return None, None, None
    return usage.prompt_tokens, usage.completion_tokens, getattr(usage, "prompt_cache_hit_tokens", None)


def to_trace(result: Result, request_id: str, lang: str, question: str, mode: str, model: str | None, prompt_id: str | None,
             client: str | None = None, code_version: str | None = None, data_version: str | None = None):
    """The `query_traces` row of a result."""
    cited = [{"label": c.label, "chunk_index": c.chunk_index, "unit": n}
             for _, citations in (result.resolved.claims if result.resolved else []) for c in citations for n in c.units]
    note = f"{len(result.resolved.dropped_ids)} ids and {result.resolved.dropped_claims} claims dropped" if (
        result.resolved and (result.resolved.dropped_ids or result.resolved.dropped_claims)) else None
    return trace.Trace(
        request_id=request_id, lang=lang, question=question, mode=mode, outcome=result.outcome, client_hash=client,
        refusal_reason=result.reason, error=result.error or note,
        retrieved=[{"label": h.label, "chunk_index": h.chunk_index, "score": h.similarity} for h in result.hits],
        cited=cited, answer=result.text if result.outcome == "answered" else None, model=model, prompt_id=prompt_id,
        tokens_in=result.tokens_in, tokens_out=result.tokens_out, tokens_cached=result.tokens_cached,
        cost_usd=result.cost_usd, retrieval_ms=result.retrieval_ms, llm_ms=result.llm_ms, total_ms=result.total_ms,
        code_version=code_version, data_version=data_version)

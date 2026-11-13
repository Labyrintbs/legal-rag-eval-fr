"""The shapes of the HTTP API (step 0f, decision 2): what a visitor sends and the one reply shape of every outcome."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from legalrag.answering import answer, search

MAX_QUESTION = 500  # characters; the longest of the 128 French gold questions has 220
MAX_COMMENT = 500
DISCLAIMER = "Informations juridiques, pas un conseil juridique. Le corpus a une date et peut ne pas contenir le droit en vigueur."


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION)
    lang: Literal["fr"] = "fr"  # the demo does not expose English

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("the question is empty")
        return value


class FeedbackRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    value: Literal[-1, 1]
    kind: Literal["wrong_answer", "wrong_citation", "missing_article", "other"] | None = None
    comment: str | None = Field(default=None, max_length=MAX_COMMENT)

    @field_validator("comment")
    @classmethod
    def blank_is_none(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class CitationOut(BaseModel):
    label: str
    units: list[int]
    passage: str
    section_path: str
    url: str


class ClaimOut(BaseModel):
    text: str
    citations: list[CitationOut]


class ArticleOut(BaseModel):
    label: str
    similarity: float
    section_path: str
    url: str
    text: str  # the best chunk of the article


class AskReply(BaseModel):
    request_id: str
    outcome: str
    reason: str | None = None
    claims: list[ClaimOut] = []
    articles: list[ArticleOut] = []
    retry_after: int | None = None
    disclaimer: str = DISCLAIMER


class SearchReply(BaseModel):
    request_id: str
    articles: list[ArticleOut]
    weak: bool  # nothing close enough was found (below the threshold of the answer path)
    disclaimer: str = DISCLAIMER


def articles_of(hits: list[search.Hit]) -> list[ArticleOut]:
    return [ArticleOut(label=h.label, similarity=round(h.similarity, 4), section_path=h.section_path, url=h.url, text=h.text)
            for h in hits]


def reply_of(result: answer.Result, request_id: str) -> AskReply:
    claims = [ClaimOut(text=text, citations=[CitationOut(label=c.label, units=c.units, passage=c.passage,
                                                         section_path=c.section_path, url=c.url) for c in citations])
              for text, citations in (result.resolved.claims if result.resolved and result.outcome == "answered" else [])]
    return AskReply(request_id=request_id, outcome=result.outcome, reason=result.reason, claims=claims,
                    articles=articles_of(result.hits), retry_after=result.retry_after)

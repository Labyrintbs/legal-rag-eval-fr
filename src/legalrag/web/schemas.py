"""The shapes of the HTTP API (step 0f, decision 2): what a visitor sends and the one reply shape of every outcome."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from legalrag.answering import answer, search

MAX_QUESTION = 500  # characters; the longest of the 128 French gold questions has 220
MAX_COMMENT = 500
DISCLAIMER = "Informations juridiques, pas un conseil juridique. Le corpus a une date et peut ne pas contenir le droit en vigueur."


# A "field" is one named entry of a message; its name is the key of the JSON the page sends.
class AskRequest(BaseModel):
    """What the page sends to /ask or /search, e.g. {"question": "Quelle durée pour un cadre ?"}."""

    question: str = Field(min_length=1, max_length=MAX_QUESTION)  # required: no default value
    lang: Literal["fr"] = "fr"  # optional (it has a default); the demo does not expose English

    @field_validator("question")  # runs on the field "question", after the length rules
    @classmethod
    def not_blank(cls, value: str) -> str:
        # "  Quelle durée ?  " is kept as "Quelle durée ?"; "   " is refused with a 422
        value = value.strip()
        if not value:
            raise ValueError("the question is empty")
        return value


class FeedbackRequest(BaseModel):
    """A vote on an answer, e.g. {"request_id": "ab12", "value": -1, "kind": "wrong_citation", "comment": "L1221-20 suffisait"}."""

    request_id: str = Field(min_length=1, max_length=64)  # the id that /ask or /search sent back
    value: Literal[-1, 1]  # 1 thumbs up, -1 thumbs down; anything else is a 422
    kind: Literal["wrong_answer", "wrong_citation", "missing_article", "other"] | None = None  # optional
    comment: str | None = Field(default=None, max_length=MAX_COMMENT)  # optional

    @field_validator("comment")
    @classmethod
    def blank_is_none(cls, value: str | None) -> str | None:
        # "  merci  " is kept as "merci"; "   " becomes None, so no empty text is stored
        return (value or "").strip() or None


class CitationOut(BaseModel):
    """The proof of a claim: the article ("L1221-19"), the exact words cited, and where to read them."""

    label: str
    units: list[int]  # which sentences or items of the article were cited, e.g. [4]
    passage: str
    section_path: str
    url: str


class ClaimOut(BaseModel):
    """One sentence of the answer with its citations, e.g. "Quatre mois pour un cadre." cited to L1221-19."""

    text: str
    citations: list[CitationOut]


class ArticleOut(BaseModel):
    """One of the 5 articles the search found, sent in every reply even when there is no answer."""

    label: str
    similarity: float
    section_path: str
    url: str
    text: str  # the best chunk of the article


# The one reply shape of /ask, whatever the outcome (decision 2). Two examples:
#   answered: {"outcome": "answered", "claims": [{"text": "...", "citations": [...]}], "articles": [...]}
#   limit hit (HTTP 429): {"outcome": "rate_limited", "reason": "...", "retry_after": 42, "claims": [], "articles": [...]}
class AskReply(BaseModel):
    request_id: str  # the page sends it back with a vote (FeedbackRequest.request_id)
    outcome: str  # "answered", "refused_by_model", "rate_limited", ... (answer.Result.outcome)
    reason: str | None = None  # why there is no answer, when there is none
    claims: list[ClaimOut] = []  # empty unless the outcome is "answered"
    articles: list[ArticleOut] = []
    retry_after: int | None = None  # seconds to wait, only for a limit
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
    """The engine's result as the reply of /ask; claims only for an answer, the articles in every case."""
    claims = [ClaimOut(text=text, citations=[CitationOut(label=c.label, units=c.units, passage=c.passage,
                                                         section_path=c.section_path, url=c.url) for c in citations])
              for text, citations in (result.resolved.claims if result.resolved and result.outcome == "answered" else [])]
    return AskReply(request_id=request_id, outcome=result.outcome, reason=result.reason, claims=claims,
                    articles=articles_of(result.hits), retry_after=result.retry_after)

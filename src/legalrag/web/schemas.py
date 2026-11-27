"""The shapes of the HTTP API (step 0f, decision 2): what a visitor sends and the one reply shape of every outcome."""

import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator

from legalrag.answering import answer, search

MAX_QUESTION = 500  # characters; the longest of the 128 French gold questions has 220
MAX_COMMENT = 500
ID_PATTERN = r"^[A-Za-z0-9_-]+$"  # a request id is 32 hexadecimal characters; nothing else is looked up
DISCLAIMER = "Informations juridiques, pas un conseil juridique. Le corpus a une date et peut ne pas contenir le droit en vigueur."


def clean_text(value: str) -> str:
    """Text as the service keeps it. A lone surrogate (JSON allows "\\ud800") cannot be written as UTF-8: refused. A control
    character other than newline and tab is dropped, and a NUL in particular would break the database."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("the text is not valid Unicode") from None
    return "".join(c for c in value if c in "\n\t" or unicodedata.category(c) != "Cc")


# A "field" is one named entry of a message; its name is the key of the JSON the page sends.
class AskRequest(BaseModel):
    """What the page sends to /ask or /search, e.g. {"question": "Quelle durée pour un cadre ?"}."""

    question: str = Field(min_length=1, max_length=MAX_QUESTION)  # required: no default value
    lang: Literal["fr"] = "fr"  # optional (it has a default); the demo does not expose English
    translate: StrictBool = False  # the visitor asked for the question to be translated into French first (a model call)

    @field_validator("question")  # runs on the field "question", after the length rules
    @classmethod
    def not_blank(cls, value: str) -> str:
        # "  Quelle durée ?  " is kept as "Quelle durée ?"; "   " (or only control characters) is refused with a 422
        value = clean_text(value).strip()
        if not value:
            raise ValueError("the question is empty")
        return value


class FeedbackRequest(BaseModel):
    """A vote on an answer, e.g. {"request_id": "ab12", "value": -1, "kind": "wrong_citation", "comment": "L1221-20 suffisait"}."""

    request_id: str = Field(min_length=1, max_length=64, pattern=ID_PATTERN)  # the id that /ask or /search sent back
    value: StrictInt  # 1 thumbs up, -1 thumbs down; anything else (a string, true, 0, 2) is a 422
    kind: Literal["wrong_answer", "wrong_citation", "missing_article", "other"] | None = None  # optional
    comment: str | None = Field(default=None, max_length=MAX_COMMENT)  # optional

    @field_validator("value")
    @classmethod
    def up_or_down(cls, value: int) -> int:
        if value not in (-1, 1):
            raise ValueError("a vote is 1 or -1")
        return value

    @field_validator("comment")
    @classmethod
    def blank_is_none(cls, value: str | None) -> str | None:
        # "  merci  " is kept as "merci"; "   " becomes None, so no empty text is stored
        return clean_text(value or "").strip() or None


class TranslateAnswerRequest(BaseModel):
    """The visitor asks for the English translation of an answer the service gave: only the id of that request."""

    request_id: str = Field(min_length=1, max_length=64, pattern=ID_PATTERN)


class Reply(BaseModel):
    """What we send. It refuses a field it does not know: AskReply(reson="...") is an error, and not a silent default
    for `reason`. FastAPI does not check an object that already is the model, so the check happens here, when it is built."""

    model_config = ConfigDict(extra="forbid")


class CitationOut(Reply):
    """The proof of a claim: the article ("L1221-19"), the exact words cited, and where to read them."""

    label: str
    units: list[int]  # which sentences or items of the article were cited, e.g. [4]
    passage: str
    section_path: str
    url: str


class ClaimOut(Reply):
    """One sentence of the answer with its citations, e.g. "Quatre mois pour un cadre." cited to L1221-19."""

    text: str
    citations: list[CitationOut]


class ArticleOut(Reply):
    """One of the 5 articles the search found, sent in every reply even when there is no answer."""

    label: str
    similarity: float
    section_path: str
    url: str
    text: str  # the best chunk of the article


# The one reply shape of /ask, whatever the outcome (decision 2). Two examples:
#   answered: {"outcome": "answered", "claims": [{"text": "...", "citations": [...]}], "articles": [...]}
#   limit hit (HTTP 429): {"outcome": "rate_limited", "reason": "...", "retry_after": 42, "claims": [], "articles": [...]}
class AskReply(Reply):
    request_id: str  # the page sends it back with a vote (FeedbackRequest.request_id)
    outcome: str  # "answered", "refused_by_model", "rate_limited", ... (answer.Result.outcome)
    reason: str | None = None  # why there is no answer, when there is none
    claims: list[ClaimOut] = []  # empty unless the outcome is "answered"
    articles: list[ArticleOut] = []
    retry_after: int | None = None  # seconds to wait, only for a limit
    busy: bool = False  # true when the limit is "one question at a time": another one from the same address is still in progress
    cached: bool = False  # true when the reply was stored by an earlier identical question (it cost nothing)
    question_fr: str | None = None  # the French question that was answered, when the visitor asked for a translation
    masked: list[str] = []  # the kinds of personal identifier masked in the question ("email", "phone"...); the page tells the visitor
    question_masked: str | None = None  # the question as it was used, with the labels, when something was masked
    disclaimer: str = DISCLAIMER


class HealthReply(Reply):
    """GET /health: {"status": "ok", "llm_enabled": true, "cache_warm": "done"}, or HTTP 503 {"status": "database_unavailable"}."""

    status: str
    llm_enabled: bool | None = None  # whether written answers are on; unknown when the database is down
    cache_warm: Literal["off", "running", "done"] | None = None  # the cache warm-up at startup; "off" without a list of questions
    llm_host: str | None = None  # the model provider's host name, when the service knows it (a name, no secret)
    llm_failing: bool | None = None  # the last calls to the model failed in a row (a key that stopped working, a provider down)


class SearchReply(Reply):
    request_id: str
    articles: list[ArticleOut]
    weak: bool  # nothing close enough was found (below the threshold of the answer path)
    masked: list[str] = []  # as in AskReply
    disclaimer: str = DISCLAIMER


class TranslateAnswerReply(Reply):
    request_id: str
    english: str  # the sentences of the answer in English, each followed by the numbers of its citations, as in the answer
    stored: bool = False  # true when the translation was made earlier: this request cost nothing


def numbered_claims(claims: list[dict]) -> list[str]:
    """The sentences of an answer, each followed by the numbers of its citations ("Quatre mois. [1][2]"). The numbers are
    given the way the page gives them: one per distinct cited passage, in the order of the sentences."""
    numbers: dict[tuple, int] = {}
    lines = []
    for claim in claims:
        marks = []
        for citation in claim["citations"]:
            key = (citation["label"], tuple(citation["units"]))
            numbers.setdefault(key, len(numbers) + 1)
            marks.append(f"[{numbers[key]}]")
        lines.append(f"{claim['text']} {''.join(marks)}".strip())
    return lines


def tidy_path(path: str) -> str:
    """The place of an article in the code, one title per level. The data keeps an older and a current title for some
    levels ("Chapitre Ier : A > Chapitre Ier : B"); the official site shows the second, so the first is dropped."""
    levels: list[str] = []
    for level in path.split(" > "):
        if levels and levels[-1].split(" : ")[0] == level.split(" : ")[0]:
            levels[-1] = level
        else:
            levels.append(level)
    return " > ".join(levels)


def articles_of(hits: list[search.Hit]) -> list[ArticleOut]:
    return [ArticleOut(label=h.label, similarity=round(h.similarity, 4), section_path=tidy_path(h.section_path), url=h.url,
                       text=h.text) for h in hits]


def reply_of(result: answer.Result, request_id: str) -> AskReply:
    """The engine's result as the reply of /ask; claims only for an answer, the articles in every case."""
    claims = [ClaimOut(text=text, citations=[CitationOut(label=c.label, units=c.units, passage=c.passage,
                                                         section_path=tidy_path(c.section_path), url=c.url) for c in citations])
              for text, citations in (result.resolved.claims if result.resolved and result.outcome == "answered" else [])]
    return AskReply(request_id=request_id, outcome=result.outcome, reason=result.reason, claims=claims,
                    articles=articles_of(result.hits), retry_after=result.retry_after)

from datetime import date

from pydantic import BaseModel, Field


class Article(BaseModel):
    uid: str
    source_code: str
    lang: str
    kind: str  # article | annex | recital
    native_id: str
    article_num: str
    title: str | None = None
    section_path: str  # unchanged from the source; cleaned only when a header is built
    body_text: str
    valid_from: date | None = None
    valid_to: date | None = None
    status: str | None = None
    content_hash: str
    source_url: str
    extra: dict = Field(default_factory=dict)


class Chunk(BaseModel):
    article_uid: str
    chunk_index: int
    lang: str
    header_text: str
    body_text: str
    embed_text: str  # header + "\n" + body (body alone when the header is empty)
    token_count: int
    extra: dict = Field(default_factory=dict)

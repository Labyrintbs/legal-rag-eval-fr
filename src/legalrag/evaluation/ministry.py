"""The ministry sheets as an independent reference (step 0f): for a question taken from a heading of a sheet of
travail-emploi.gouv.fr, the section of that sheet under the heading is the ministry's own answer. The check asks whether
our answer contradicts it. The sheets are a local file (`data/external/fiches-travail.json`), never committed.
"""

import json
import re
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel, field_validator

Label = Literal["agrees", "not covered", "contradicts"]
LABELS = get_args(Label)


class Verdict(BaseModel):
    reason: str = ""
    label: Label

    @field_validator("label", mode="before")
    @classmethod
    def lowercase(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


def normalise(text: str) -> str:
    """Headings differ between the sheets and our questions in non-breaking spaces, apostrophes and case."""
    return re.sub(r"\s+", " ", text.replace("’", "'").replace("\xa0", " ")).strip().lower()


def load_sheets(path: Path) -> dict[str, dict]:
    """url -> sheet."""
    return {sheet["url"]: sheet for sheet in json.loads(path.read_text())}


def official_text(sheets: dict[str, dict], url: str, heading: str) -> str | None:
    """The text of the section of the sheet whose title is the heading; none when the sheet or the section is missing."""
    sheet = sheets.get(url)
    wanted = normalise(heading)
    return next((s["text"] for s in sheet["sections"] if normalise(s["title"]) == wanted), None) if sheet else None

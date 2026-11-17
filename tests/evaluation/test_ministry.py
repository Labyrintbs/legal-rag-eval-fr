import json

import pytest
from pydantic import ValidationError

from legalrag.evaluation import ministry

SHEETS = {"https://x/rss": {"url": "https://x/rss", "sections": [
    {"title": "Quelles sont les missions du représentant\xa0?", "text": "Il assure l'interface."},
    {"title": "Qui peut le désigner\xa0?", "text": "Un syndicat."}]}}


def test_a_heading_matches_its_section_despite_non_breaking_spaces_apostrophes_and_case():
    assert ministry.official_text(SHEETS, "https://x/rss", "Quelles sont les missions du représentant ?") == "Il assure l'interface."
    assert ministry.official_text(SHEETS, "https://x/rss", "QUI PEUT LE DÉSIGNER ?") == "Un syndicat."


def test_a_missing_sheet_or_section_gives_none():
    assert ministry.official_text(SHEETS, "https://x/other", "Qui peut le désigner ?") is None
    assert ministry.official_text(SHEETS, "https://x/rss", "Autre question ?") is None


def test_sheets_are_loaded_by_url(tmp_path):
    path = tmp_path / "sheets.json"
    path.write_text(json.dumps(list(SHEETS.values())))
    assert set(ministry.load_sheets(path)) == {"https://x/rss"}


def test_the_verdict_takes_the_three_labels_only():
    assert ministry.Verdict.model_validate_json('{"label": "Contradicts"}').label == "contradicts"
    with pytest.raises(ValidationError):
        ministry.Verdict.model_validate_json('{"label": "partly"}')

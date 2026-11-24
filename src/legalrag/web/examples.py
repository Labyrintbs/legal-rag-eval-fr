"""The example questions of the demo page: one YAML file (`examples.yaml`) that the page shows as cards and that
`warm` asks at startup, so that a click gets a stored reply."""

from pathlib import Path

import yaml

EXAMPLES_FILE = Path(__file__).with_name("examples.yaml")
SOURCES = ("ct", "gdpr", "none")  # Code du travail, RGPD, outside the texts: the tag and colour of the card


def load(path: Path = EXAMPLES_FILE) -> list[dict]:
    """[{"question": ..., "question_en": its English description or None, "source": "ct", "label": {"fr": ..., "en": ...}}];
    an entry that is a plain text has the source "none" and its question as label."""
    out = []
    for entry in yaml.safe_load(path.read_text())["questions"]:
        question = entry if isinstance(entry, str) else entry["question"]
        mapping = {} if isinstance(entry, str) else entry
        label = mapping.get("label", {})
        out.append({"question": question.strip(), "source": mapping.get("source", "none"), "question_en": mapping.get("question_en"),
                    "label": {"fr": label.get("fr", question), "en": label.get("en", label.get("fr", question))}})
    return out

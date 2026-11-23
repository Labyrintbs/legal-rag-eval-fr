"""The cache warm-up (step 0f, decision 4): the example questions asked once through the real path, so that the first
visitor who clicks an example gets a stored reply. The service runs it in the background at startup, and
`legalrag cache warm` runs it by hand. It skips what is already cached (a restart costs nothing), never fails the
launch, and stops when the model is switched off, the daily budget is used up or the model fails.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

from legalrag.answering import cache, rag
from legalrag.answering.logs import log_event
from legalrag.web import asking

log = logging.getLogger("legalrag.web")
STOPS = ("llm_disabled", "rate_limited", "llm_error", "parse_error")  # nothing more would work now


@dataclass
class Status:
    state: str = "off"  # off (no questions), running, done
    asked: int = 0
    stored: int = 0
    skipped: int = 0  # already cached
    stopped: str | None = None  # the outcome that stopped the run, if any


def load_questions(path: Path) -> list[str]:
    """A YAML file: a list of questions, or {"questions": [...]}."""
    data = yaml.safe_load(path.read_text())
    questions = data["questions"] if isinstance(data, dict) else data
    if not isinstance(questions, list) or not all(isinstance(q, str) and q.strip() for q in questions):
        raise ValueError(f"{path}: expected a list of questions")
    return [q.strip() for q in questions]


def pending(engine: rag.AnswerEngine, connect, settings: asking.Settings, questions: list[str]) -> list[str]:
    """The questions that are not cached yet."""
    with connect() as conn:
        return [q for q in questions if cache.get(conn, asking.cache_key(engine, settings, q), count=False) is None]


def run(engine: rag.AnswerEngine, connect, settings: asking.Settings, questions: list[str], status: Status) -> Status:
    """Ask each question that is not cached yet. Never raises: a failure is logged and ends the run."""
    status.state = "running"
    try:
        todo = pending(engine, connect, settings, questions)
        status.skipped = len(questions) - len(todo)
        for question in todo:
            reply, _ = asking.answer_question(engine, connect, settings, question, client=None, warm=True)
            status.asked += 1
            if reply.outcome in cache.CACHEABLE:
                status.stored += 1
            elif reply.outcome in STOPS:
                status.stopped = reply.outcome
                break
            else:  # an example that has no stable reply (weak search, invalid citation): worth knowing
                log_event(log, "warm_not_cached", reply.request_id, logging.WARNING, outcome=reply.outcome)
    except Exception as error:  # noqa: BLE001 - the warm-up must never stop the service
        status.stopped = type(error).__name__
        log_event(log, "warm_failed", None, logging.ERROR, error=type(error).__name__)
    status.state = "done"
    log_event(log, "warm_done", None, asked=status.asked, stored=status.stored, skipped=status.skipped, stopped=status.stopped)
    return status

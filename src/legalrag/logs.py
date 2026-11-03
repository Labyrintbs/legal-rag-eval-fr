"""Logs to stdout as JSON lines (plan: logs to stdout), one event per line with a request id. Question and answer
text never go into a log: logs are less controlled than the database, which has a retention rule.
"""

import json
import logging
import sys
from datetime import UTC, datetime

FORBIDDEN = {"question", "answer", "text", "ip", "address", "client", "query"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {"time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
                 "level": record.levelname, "logger": record.name, "event": record.getMessage(),
                 **getattr(record, "fields", {})}
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info).splitlines()[-1]
        return json.dumps(entry, ensure_ascii=False, default=str)


def setup(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


def log_event(logger: logging.Logger, event: str, request_id: str | None = None, level: int = logging.INFO, **fields) -> None:
    """One structured event. A field that could carry personal data is refused, not silently dropped."""
    if banned := FORBIDDEN & set(fields):
        raise ValueError(f"not allowed in a log: {sorted(banned)}")
    logger.log(level, event, extra={"fields": {"request_id": request_id, **fields}})

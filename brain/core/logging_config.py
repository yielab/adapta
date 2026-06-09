"""Logging configuration — plain text (default) or structured JSON (§3.5).

Toggle with BRAIN_LOG_FORMAT=json. JSON logs are easier to ship to a log
aggregator; text stays the friendly default for local dev.
"""

from __future__ import annotations

import json
import logging
import sys

from brain.config import settings

_TEXT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        cid = getattr(record, "cid", None)
        if cid:
            payload["correlation_id"] = cid
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging() -> None:
    """Install a single root handler honoring BRAIN_LOG_FORMAT. Idempotent."""
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format.strip().lower() == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(logging.Formatter(_TEXT_FORMAT))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

"""
Centralized logging configuration.

Two things get imported from this file elsewhere in the project:
    - `logger`: import this and call logger.info("event_name", extra={...})
      -- this is the pattern used throughout every service, tool, and
      graph node in this codebase.
    - `setup_logging()`: call this ONCE, at app startup (in main.py,
      before the FastAPI app starts serving requests). It configures
      output format and handlers; nothing will log correctly formatted
      until this runs.

Design choices:
    - JSON output, not plain text. Every log line becomes one JSON object
      on stdout, with any extra={...} fields folded in. This matters for
      Phase 9 (observability) later -- structured logs are what a real
      log aggregator (CloudWatch, Datadog, ELK, etc.) actually needs;
      plain-text logs with inconsistent formatting are painful to query.
    - Logs go to stdout only, not a file. This matches how containerized
      apps are expected to log (Docker/Kubernetes capture stdout and ship
      it elsewhere) -- writing to a local file is the wrong pattern once
      this is Dockerized in Phase 10.
    - Third-party libraries (httpx, urllib3, langchain internals) are
      quieted to WARNING by default -- they're chatty at INFO and drown
      out your own application's logs otherwise. Your own logger stays
      at INFO (or whatever LOG_LEVEL is set to).
    - NEVER log secrets. Passwords, JWTs, API keys, full card numbers,
      or raw payment details must never end up in a log line, structured
      or not -- this is a hard rule from the project doc's Phase 9
      section, not just a style preference. When logging something that
      touches these, log an identifier (e.g. transaction_reference) or a
      masked form, never the raw value.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

APP_LOGGER_NAME = "shopflow"

# Standard LogRecord attributes -- anything NOT in this set on a record is
# something the caller passed via extra={...} and should be included in
# the JSON output.
_STANDARD_LOG_RECORD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName",
}


class JSONFormatter(logging.Formatter):
    """Formats each log record as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Fold in anything passed via extra={...}.
        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_RECORD_ATTRS and key not in log_entry:
                log_entry[key] = value

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_logging(level: str | None = None) -> None:
    """
    Configures the app's logging. Call this exactly once, at startup
    (e.g. in main.py before the app is created / before any routes can
    receive traffic). Safe to call more than once -- it clears existing
    handlers first rather than stacking duplicate ones, which matters
    with `fastapi dev`'s auto-reload re-executing your module.
    """
    resolved_level = (level or os.environ.get("LOG_LEVEL") or "INFO").upper()

    app_logger = logging.getLogger(APP_LOGGER_NAME)
    app_logger.setLevel(resolved_level)
    app_logger.handlers.clear()
    app_logger.propagate = False  # don't also send through the root logger's handlers

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    app_logger.addHandler(handler)

    # Quiet down noisy third-party libraries -- they log plenty at INFO
    # that isn't useful for you and drowns out application logs.
    for noisy_logger_name in ("httpx", "httpcore", "urllib3", "google_genai", "langchain"):
        logging.getLogger(noisy_logger_name).setLevel(logging.WARNING)


# The single logger instance every other file in the project imports:
#     from backend.core.logging import logger
#     logger.info("order_created", extra={"order_id": str(order.id)})
logger = logging.getLogger(APP_LOGGER_NAME)
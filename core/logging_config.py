"""
╔══════════════════════════════════════════════════════════════════════╗
║  core/logging_config.py — نظام التسجيل الاحترافي                   ║
║  يدعم: Console + File Rotation + JSON Structured Logs               ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class StructuredJSONFormatter(logging.Formatter):
    """
    Formats log records as structured JSON lines — compatible with log
    aggregators such as Elasticsearch, Loki, or Datadog.

    Each line is a JSON object with:
        timestamp, level, logger, message, + any extra fields passed
        via ``extra={}`` in the log call.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        # Allow callers to attach arbitrary structured fields
        for key, value in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "levelname", "levelno",
                "pathname", "filename", "module", "exc_info", "exc_text",
                "stack_info", "lineno", "funcName", "created", "msecs",
                "relativeCreated", "thread", "threadName", "process",
                "processName", "message",
            ):
                log_entry[key] = value

        return json.dumps(log_entry, ensure_ascii=False, default=str)


def setup_logging(
    level: str = "INFO",
    log_dir: Path | None = None,
    json_format: bool = False,
) -> None:
    """
    Configure the root logger with console and optional rotating-file handlers.

    Args:
        level: Logging level string (e.g. "DEBUG", "INFO", "WARNING").
        log_dir: If provided, logs are also written to daily-rotated files.
        json_format: If True, use structured JSON formatter for file logs.

    Examples:
        >>> setup_logging(level="DEBUG", log_dir=Path("/app/logs"))
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # ── Console handler (human-readable) ─────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    handlers: list[logging.Handler] = [console_handler]

    # ── File handler (rotating, optional) ────────────────────────────
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=log_dir / "lms_bot.log",
            when="midnight",
            backupCount=30,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(
            StructuredJSONFormatter() if json_format
            else logging.Formatter(
                fmt="%(asctime)s | %(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        handlers.append(file_handler)

    logging.basicConfig(
        level=numeric_level,
        handlers=handlers,
        force=True,
    )

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "telegram.ext.Application"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

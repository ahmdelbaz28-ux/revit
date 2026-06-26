from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
from pathlib import Path
from typing import Any

_SENSITIVE_PATTERNS: list[re.Pattern] = [
    re.compile(r'(?i)(api[_-]?key|apikey|secret|password|token|credential|auth[_-]?token)["\']?\s*[:=]\s*["\']?([^"\'&\s,;}]+)'),
    re.compile(r'(?i)(Authorization|Bearer)\s+(\S+)'),
    re.compile(r'\b[3-5]\d{3}\s+\d{4}\s+\d{4}\s+\d{4}\b'),
    re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
]


def mask_sensitive(value: str) -> str:
    """Redact API keys, tokens, credit-card and SSN patterns from a string."""
    for pattern in _SENSITIVE_PATTERNS:
        value = pattern.sub(lambda m: m.group(1) + '="***"' if m.lastindex and m.lastindex >= 2 else '***', value)
    return value


class JSONFormatter(logging.Formatter):
    def __init__(self, service_name: str = 'fireai') -> None:
        """Initialise the formatter with the given service name."""
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string with trace context and sensitive-data masking."""
        log_entry: dict[str, Any] = {
            'timestamp': self.formatTime(record, datefmt='%Y-%m-%dT%H:%M:%S.%fZ'),
            'level': record.levelname,
            'logger': record.name,
            'message': mask_sensitive(record.getMessage()),
            'service': self.service_name,
        }

        if hasattr(record, 'trace_id') and record.trace_id:
            log_entry['trace_id'] = record.trace_id
        if hasattr(record, 'span_id') and record.span_id:
            log_entry['span_id'] = record.span_id

        if record.exc_info and record.exc_info[0]:
            log_entry['exception'] = self.formatException(record.exc_info)

        if hasattr(record, 'extra_data'):
            log_entry['extra'] = record.extra_data

        return json.dumps(log_entry, default=str)


class AsyncLogHandler(logging.handlers.RotatingFileHandler):
    def emit(self, record: logging.LogRecord) -> None:
        """Write a formatted log record to the rotating log file."""
        try:
            msg = self.format(record)
            with open(self.baseFilename, 'a') as f:
                f.write(msg + '\n')
        except Exception:
            self.handleError(record)


def setup_logging(
    service_name: str,
    level: str = 'INFO',
    log_dir: str | None = None,
) -> logging.Logger:
    """Configure structured JSON logging with file rotation and console output."""
    if log_dir is None:
        log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'data', 'logs'
        )
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(service_name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    log_path = os.path.join(log_dir, f'{service_name}.log')
    handler = AsyncLogHandler(
        log_path,
        maxBytes=100 * 1024 * 1024,
        backupCount=10,
    )
    handler.setFormatter(JSONFormatter(service_name=service_name))
    logger.addHandler(handler)

    console = logging.StreamHandler()
    console.setFormatter(JSONFormatter(service_name=service_name))
    logger.addHandler(console)

    return logger


def add_trace_to_record(logger: logging.Logger, trace_id: str, span_id: str) -> None:
    """Attach trace_id and span_id to every log record emitted by *logger*."""
    class TraceFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            """Inject trace identifiers into the log record."""
            record.trace_id = trace_id
            record.span_id = span_id
            return True

    for handler in logger.handlers:
        handler.addFilter(TraceFilter())

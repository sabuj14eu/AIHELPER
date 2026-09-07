"""Structured logging with a redaction processor.

Two rules this module exists to enforce:
  * secrets never reach a log line;
  * every log line carries the request_id so a request can be reconstructed.

Document contents and message bodies are NOT logged. Only lengths, hashes and
metadata are. See docs/security.md.
"""

from __future__ import annotations

import contextlib
import logging
import re
import sys
import threading
from contextvars import ContextVar
from typing import Any

import structlog

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
client_id_var: ContextVar[str | None] = ContextVar("client_id", default=None)

# Keys whose values are replaced wholesale, wherever they appear.
SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "password",
    "passwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "auth_secret",
    "openai_api_key",
    "anthropic_api_key",
    "qdrant_api_key",
    "cookie",
    "set-cookie",
    "session",
    "private_key",
    "credential",
    "credentials",
    # payload bodies — never logged
    "message",
    "prompt",
    "answer",
    "content",
    "text",
    "document",
    "chunk",
}

REDACTED = "[REDACTED]"

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"ahk_[A-Za-z0-9]{6,}\.[A-Za-z0-9_\-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{12,}"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
]


def scrub_text(value: str) -> str:
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub(REDACTED, value)
    return value


def _redact(obj: Any, depth: int = 0) -> Any:
    if depth > 6:
        return REDACTED
    if isinstance(obj, dict):
        out = {}
        for key, val in obj.items():
            if str(key).lower() in SENSITIVE_KEYS:
                out[key] = REDACTED
            else:
                out[key] = _redact(val, depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return [_redact(v, depth + 1) for v in obj][:50]
    if isinstance(obj, str):
        return scrub_text(obj)
    return obj


def redaction_processor(_logger, _name, event_dict):  # pragma: no cover - trivial
    return _redact(event_dict)


def context_processor(_logger, _name, event_dict):  # pragma: no cover - trivial
    rid = request_id_var.get()
    if rid:
        event_dict.setdefault("request_id", rid)
    cid = client_id_var.get()
    if cid:
        event_dict.setdefault("client_id", cid)
    return event_dict


class _StderrLogger:
    """A logger that resolves ``sys.stderr`` at write time.

    structlog's PrintLoggerFactory captures the stream object when the logger
    is built. Anything that later replaces the stream — pytest's capture, a
    supervisor rotating file descriptors — leaves the cached logger writing to
    a closed file. Looking the stream up per call costs an attribute lookup and
    removes the whole failure mode.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def msg(self, message: str) -> None:
        # The stream can be gone (closed, replaced). Losing a log line is not
        # worth losing the request that was being logged.
        with self._lock, contextlib.suppress(ValueError, OSError):
            print(message, file=sys.stderr, flush=True)

    log = debug = info = warning = error = critical = exception = failure = msg


class _StderrLoggerFactory:
    def __call__(self, *_args):
        return _StderrLogger()


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Configure structured logging.

    Logs go to **stderr**, not stdout. Docker and every log collector capture
    both, and keeping stdout clean means a command's machine-readable output
    (``python -m app.cli create-client`` emitting JSON, for instance) is never
    interleaved with log lines.
    """
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    renderer = (
        structlog.processors.JSONRenderer()
        if fmt == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            context_processor,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redaction_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=_StderrLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "ai_helper"):
    return structlog.get_logger(name)

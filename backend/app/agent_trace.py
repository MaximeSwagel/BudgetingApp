"""Opt-in per-provider JSON-lines trace files for categorization agents.

Unlike stdout events these records carry full inputs and outputs (descriptions,
amounts, prompts), so they are written only when AGENT_LOG_DIR is set. A trace
problem must never fail a categorize run: any error emits one sanitized warning
and turns tracing off for the rest of the process.
"""

import contextlib
import contextvars
import hashlib
import json
import logging
import logging.handlers
import os
import re
import sys
import uuid
from datetime import datetime, timezone

from app.config import settings
from app.observability import log_event

TRACE_MAX_BYTES = 10 * 1024 * 1024
TRACE_BACKUPS = 5

_PROVIDER_RE = re.compile(r"[a-z0-9_-]+")
_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("agent_trace_run_id", default=None)
_handlers: dict[str, tuple[str, logging.Handler, logging.Logger]] = {}
_disabled = False
_warn_logger = logging.getLogger("app.agent_trace")


def _disable(exc: BaseException | None) -> None:
    global _disabled
    if _disabled:
        return
    _disabled = True
    # Class name only: the exception text can carry paths or record content.
    log_event(
        _warn_logger, "agent_trace", level=logging.WARNING, ok=False, disabled=True,
        error=type(exc).__name__ if exc is not None else "unknown",
    )


class _TraceFileHandler(logging.handlers.RotatingFileHandler):
    def __init__(self, path: str):
        super().__init__(path, maxBytes=TRACE_MAX_BYTES, backupCount=TRACE_BACKUPS, encoding="utf-8")

    def _open(self):
        fd = os.open(self.baseFilename, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        stream = os.fdopen(fd, "a", encoding="utf-8")
        os.chmod(self.baseFilename, 0o600)
        return stream

    def handleError(self, record):
        # The stdlib would print the traceback and the record (financial data) to stderr.
        _disable(sys.exc_info()[1])


def _close(entry: tuple[str, logging.Handler, logging.Logger]) -> None:
    _, handler, logger = entry
    logger.removeHandler(handler)
    handler.close()


def _logger_for(provider: str) -> logging.Logger:
    directory = settings.agent_log_dir.strip()
    entry = _handlers.get(provider)
    if entry is not None and entry[0] == directory:
        return entry[2]
    if entry is not None:
        _close(entry)
        del _handlers[provider]
    # An existing directory is never chmodded: the operator owns it.
    os.makedirs(directory, mode=0o700, exist_ok=True)
    handler = _TraceFileHandler(os.path.join(directory, f"{provider}.log"))
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger(f"agent_trace.{provider}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)
    _handlers[provider] = (directory, handler, logger)
    return logger


def enabled() -> bool:
    return bool(settings.agent_log_dir.strip()) and not _disabled


@contextlib.contextmanager
def trace_run():
    run_id = uuid.uuid4().hex[:12]
    token = _run_id.set(run_id)
    try:
        yield run_id
    finally:
        _run_id.reset(token)


def current_run_id() -> str | None:
    return _run_id.get()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def write(provider: str, record: dict) -> None:
    try:
        if not enabled() or not _PROVIDER_RE.fullmatch(provider):
            return
        logger = _logger_for(provider)
        line = json.dumps(
            {"ts": _now(), "run_id": current_run_id(), "provider": provider, **record},
            ensure_ascii=False, default=str,
        )
        logger.info(line)
    except Exception as e:
        _disable(e)


def prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def taxonomy_hash(categories: dict[str, list[str]]) -> str:
    """Order-sensitive on purpose: a reordered hierarchy changes what the agents see."""
    text = json.dumps(list(categories.items()), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def reset() -> None:
    global _disabled
    for entry in list(_handlers.values()):
        _close(entry)
    _handlers.clear()
    _disabled = False

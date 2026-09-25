"""Log observability helpers.

Watching the backend live with `docker logs -f` on the dev EC2 box needs
single-line, greppable, key=value, UTC-timestamped lines. This module provides:

- a UTC ISO-8601 (millisecond, Z suffix) log format applied to every logger,
  uvicorn's own included;
- render_event / log_event, which emit `event=<name> k=v ...` lines;
- RequestTimingMiddleware, one duration line per HTTP request.

Only counts, codes and timings should ever be passed to log_event. Never put
descriptions, amounts, CSV content, API keys or query-string values in a line.
"""

import json
import logging
import logging.config
import time

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class UtcIsoFormatter(logging.Formatter):
    """Renders asctime as 2026-09-25T14:03:07.123Z (UTC).

    The stdlib appends msecs via default_msec_format only when datefmt is None,
    so never pass a datefmt to this formatter.
    """

    converter = time.gmtime
    default_time_format = "%Y-%m-%dT%H:%M:%S"
    default_msec_format = "%s.%03dZ"


LOGGING_CONFIG = {
    "version": 1,
    # app.main imports every router (and so creates its logger) before this
    # runs; leaving existing loggers enabled keeps them alive.
    "disable_existing_loggers": False,
    "formatters": {"utc_iso": {"()": UtcIsoFormatter, "fmt": LOG_FORMAT}},
    "handlers": {
        "stderr": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "utc_iso",
        }
    },
    "root": {"level": "INFO", "handlers": ["stderr"]},
    # uvicorn installs its own unstamped, colourised handlers (propagate False)
    # before importing the app. Listing these loggers clears those handlers and
    # routes their records through the stamped root handler. uvicorn's
    # access_log flag uses hasHandlers(), which follows propagation, so access
    # lines keep flowing.
    "loggers": {
        "uvicorn": {"level": "INFO", "handlers": [], "propagate": True},
        "uvicorn.error": {"level": "INFO", "handlers": [], "propagate": True},
        "uvicorn.access": {"level": "INFO", "handlers": [], "propagate": True},
    },
}


def configure_logging() -> None:
    logging.config.dictConfig(LOGGING_CONFIG)


def elapsed_ms(start: float) -> float:
    """Milliseconds since a time.perf_counter() start value."""
    return (time.perf_counter() - start) * 1000


def _render_value(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.1f}"
    if isinstance(value, int):
        return str(value)
    text = value if isinstance(value, str) else str(value)
    if text == "" or any(c.isspace() or c in '"=' or not c.isprintable() for c in text):
        return json.dumps(text, ensure_ascii=False)
    return text


def render_event(event: str, **fields: object) -> str:
    parts = [f"event={event}"]
    parts.extend(f"{key}={_render_value(value)}" for key, value in fields.items())
    return " ".join(parts)


def log_event(logger: logging.Logger, event: str, *, level: int = logging.INFO, **fields: object) -> None:
    # Pre-rendered and passed without args so a literal % in a path can't trip
    # %-formatting.
    logger.log(level, render_event(event, **fields))


_access_logger = logging.getLogger("app.access")


class RequestTimingMiddleware:
    """Pure ASGI middleware (not BaseHTTPMiddleware) so uploads and streaming
    are untouched. Logs scope["path"] only, never the query string."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status = 500

        async def send_wrapper(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            log_event(
                _access_logger,
                "request",
                method=scope["method"],
                path=scope["path"],
                status=status,
                ms=elapsed_ms(start),
            )

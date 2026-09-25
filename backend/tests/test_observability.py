"""Tests for app.observability: stamped log format, key=value events, request timing.

The real-uvicorn smoke test is the key regression guard: uvicorn installs its own
unstamped handlers before importing the app, so only a run through the actual CLI
proves that our import-time dictConfig wins.
"""

import logging
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

import app.main  # noqa: F401  (import applies configure_logging)
from app.observability import LOG_FORMAT, UtcIsoFormatter, render_event

STAMP = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z"


def test_render_event_basic_order_and_tokens():
    assert render_event("csv_parse", parser="ca", rows=120, ms=14.2) == "event=csv_parse parser=ca rows=120 ms=14.2"


def test_render_event_floats_bools_none():
    assert render_event("x", ms=3.14159) == "event=x ms=3.1"
    assert render_event("x", ms=0.0) == "event=x ms=0.0"
    assert render_event("x", a=True, b=False, c=None) == "event=x a=true b=false c=-"


def test_render_event_quotes_unsafe_strings():
    assert render_event("x", bank="Crédit Agricole") == 'event=x bank="Crédit Agricole"'
    assert render_event("x", v="") == 'event=x v=""'
    assert render_event("x", v="a=b") == 'event=x v="a=b"'
    out = render_event("x", path="/a\nb")
    assert "\n" not in out
    assert '"/a\\nb"' in out


def test_utc_iso_formatter_exact_output():
    record = logging.makeLogRecord(
        {"name": "app.test", "levelname": "INFO", "msg": "hello", "created": 0.5, "msecs": 500.0}
    )
    assert UtcIsoFormatter(LOG_FORMAT).format(record) == "1970-01-01T00:00:00.500Z INFO app.test hello"


def _stamped_root_formatter():
    for handler in logging.getLogger().handlers:
        if isinstance(handler.formatter, UtcIsoFormatter):
            return handler.formatter
    return None


def test_logger_wiring_after_import():
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        assert lg.handlers == []
        assert lg.propagate is True
    assert _stamped_root_formatter() is not None
    assert logging.getLogger("app.routers.upload").disabled is False


def test_uvicorn_access_record_is_stamped():
    formatter = _stamped_root_formatter()
    assert formatter is not None
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '%s - "%s %s HTTP/%s" %d', ("127.0.0.1:5000", "GET", "/api/health", "1.1", 200), None,
    )
    assert re.match(
        rf'^{STAMP} INFO uvicorn\.access 127\.0\.0\.1:5000 - "GET /api/health HTTP/1\.1" 200$',
        formatter.format(record),
    )


async def test_request_middleware_logs_one_line_without_query(client, caplog):
    caplog.set_level(logging.INFO)
    resp = await client.get("/api/health?token=s3cr3t")
    assert resp.status_code == 200
    records = [r for r in caplog.records if r.name == "app.access"]
    assert len(records) == 1
    assert re.match(
        r"^event=request method=GET path=/api/health status=200 ms=\d+\.\d$", records[0].getMessage()
    )
    # httpx's own client logger echoes the URL; only the app's records are in scope.
    assert all("s3cr3t" not in r.getMessage() for r in caplog.records if r.name.startswith("app."))


async def test_request_middleware_logs_404(client, caplog):
    caplog.set_level(logging.INFO)
    await client.get("/api/does-not-exist")
    records = [r for r in caplog.records if r.name == "app.access"]
    assert len(records) == 1
    assert "status=404" in records[0].getMessage()


def test_real_uvicorn_cli_lines_are_stamped(tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    backend_dir = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path}/smoke.db"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=backend_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.time() + 20
        ok = False
        while time.time() < deadline:
            try:
                r = httpx.get(f"http://127.0.0.1:{port}/api/health?token=s3cr3t", timeout=2)
                if r.status_code == 200:
                    ok = True
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        assert ok, "server never became healthy"
        proc.terminate()
        output, _ = proc.communicate(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()

    lines = output.splitlines()
    for line in lines:
        assert not line.startswith(("INFO:", "WARNING:", "ERROR:")), line
        if " uvicorn." in line or " app." in line:
            assert re.match(rf"^{STAMP} (DEBUG|INFO|WARNING|ERROR|CRITICAL) ", line), line

    assert any("INFO uvicorn.error Started server process" in ln for ln in lines)
    assert any("INFO uvicorn.access" in ln and "GET /api/health" in ln for ln in lines)
    assert any(
        "INFO app.access event=request method=GET path=/api/health status=200 ms=" in ln for ln in lines
    )
    assert not any("app.access" in ln and "s3cr3t" in ln for ln in lines)

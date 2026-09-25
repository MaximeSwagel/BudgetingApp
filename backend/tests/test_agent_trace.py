"""Opt-in per-provider agent trace files. No network; all file I/O in tmp_path."""

import json
import logging
import re
import stat
from types import SimpleNamespace

import pytest

from app import agent_trace
from app.config import settings
from app.services import classifier
from app.services.agents import llm as llm_mod
from app.services.agents.base import CategorizationAgent
from app.services.agents.llm import PROMPT_HASH, OpenAiAgent

KEY = "sk-SENTINEL-KEY"
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
GOOD = {"general_category": "Household Expenses", "precise_category": "Groceries"}


def _txns(n=2):
    base = [
        {"description": "Tesco", "original_amount": "20.00", "original_currency": "ILS", "bank": "Revolut"},
        {"description": "Weird Merchant", "original_amount": "8.50", "original_currency": "ILS", "bank": "Revolut"},
    ]
    return base[:n] if n <= 2 else [dict(base[0]) for _ in range(n)]


def _set_dir(monkeypatch, tmp_path):
    d = tmp_path / "agent-logs"
    monkeypatch.setattr(settings, "agent_log_dir", str(d))
    return d


def _records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _agent_trace_warnings(caplog):
    return [
        r.getMessage() for r in caplog.records
        if r.levelno == logging.WARNING and "event=agent_trace" in r.getMessage()
    ]


def _fake_openai(create):
    class FakeOpenAI:
        def __init__(self, api_key=None):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

    return FakeOpenAI


def _fake_anthropic(create):
    class FakeAnthropic:
        def __init__(self, api_key=None):
            self.messages = SimpleNamespace(create=create)

    return FakeAnthropic


def _openai_response(results, usage=None):
    content = json.dumps({"results": results})
    resp = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
    if usage is not None:
        resp.usage = usage
    return resp


@pytest.fixture
def openai_settings(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", KEY)
    monkeypatch.setattr(settings, "openai_model", "gpt-test")
    monkeypatch.setattr(settings, "anthropic_api_key", KEY)
    monkeypatch.setattr(settings, "anthropic_model", "claude-test")


# ---- writer ----------------------------------------------------------------


def test_unset_dir_writes_nothing(tmp_path):
    assert agent_trace.enabled() is False
    agent_trace.write("openai", {"stage": "batch"})
    assert list(tmp_path.iterdir()) == []


def test_write_creates_file_with_perms_and_fields(monkeypatch, tmp_path):
    d = _set_dir(monkeypatch, tmp_path)
    with agent_trace.trace_run() as run_id:
        agent_trace.write("openai", {"model": "m", "stage": "batch", "x": 1})
    assert stat.S_IMODE(d.stat().st_mode) == 0o700
    f = d / "openai.log"
    assert stat.S_IMODE(f.stat().st_mode) == 0o600
    (rec,) = _records(f)
    assert TS_RE.match(rec["ts"])
    assert rec["run_id"] == run_id
    assert rec["provider"] == "openai" and rec["x"] == 1


def test_run_id_null_outside_run(monkeypatch, tmp_path):
    d = _set_dir(monkeypatch, tmp_path)
    agent_trace.write("openai", {"stage": "batch"})
    assert _records(d / "openai.log")[0]["run_id"] is None
    assert agent_trace.current_run_id() is None


def test_separate_files_per_provider(monkeypatch, tmp_path):
    d = _set_dir(monkeypatch, tmp_path)
    agent_trace.write("openrouter", {"stage": "line"})
    agent_trace.write("anthropic", {"stage": "batch"})
    assert [r["provider"] for r in _records(d / "openrouter.log")] == ["openrouter"]
    assert [r["provider"] for r in _records(d / "anthropic.log")] == ["anthropic"]


def test_rotation_keeps_0600(monkeypatch, tmp_path):
    d = _set_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(agent_trace, "TRACE_MAX_BYTES", 200)
    for i in range(10):
        agent_trace.write("openai", {"stage": "batch", "pad": "x" * 60, "i": i})
    rotated = d / "openai.log.1"
    assert rotated.exists()
    assert stat.S_IMODE(rotated.stat().st_mode) == 0o600
    assert stat.S_IMODE((d / "openai.log").stat().st_mode) == 0o600


def test_unsafe_provider_name_writes_nothing(monkeypatch, tmp_path):
    d = _set_dir(monkeypatch, tmp_path)
    agent_trace.write("../evil", {"stage": "batch"})
    assert not d.exists() or list(d.iterdir()) == []
    assert not (tmp_path / "evil.log").exists()


def test_setup_failure_warns_once_and_disables(monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO)
    (tmp_path / "f").write_text("x")
    monkeypatch.setattr(settings, "agent_log_dir", str(tmp_path / "f" / "sub"))
    agent_trace.write("openai", {"stage": "batch"})
    agent_trace.write("openai", {"stage": "batch"})
    (warning,) = _agent_trace_warnings(caplog)
    assert "ok=false" in warning and "error=" in warning
    assert str(tmp_path) not in warning
    assert agent_trace.enabled() is False


def test_emit_failure_is_silent_on_std_streams(monkeypatch, tmp_path, caplog, capsys):
    caplog.set_level(logging.INFO)
    _set_dir(monkeypatch, tmp_path)
    agent_trace.write("openai", {"stage": "batch"})

    def boom(self, record):
        raise OSError("disk gone")

    monkeypatch.setattr(agent_trace._TraceFileHandler, "shouldRollover", boom)
    agent_trace.write("openai", {"stage": "batch", "d": "SENSITIVE-DESC"})
    agent_trace.write("openai", {"stage": "batch", "d": "SENSITIVE-DESC"})
    assert len(_agent_trace_warnings(caplog)) == 1
    out = capsys.readouterr()
    for stream in (out.out, out.err):
        assert "SENSITIVE-DESC" not in stream and "Traceback" not in stream
    assert agent_trace.enabled() is False


def test_records_do_not_propagate(monkeypatch, tmp_path):
    # caplog also hooks non-propagating loggers, so watch the root logger directly.
    seen = []

    class Spy(logging.Handler):
        def emit(self, record):
            seen.append(record.getMessage())

    spy = Spy(logging.NOTSET)
    root = logging.getLogger()
    root.addHandler(spy)
    try:
        _set_dir(monkeypatch, tmp_path)
        agent_trace.write("openai", {"stage": "batch", "d": "SENSITIVE-DESC"})
    finally:
        root.removeHandler(spy)
    assert logging.getLogger("agent_trace.openai").propagate is False
    assert all("SENSITIVE-DESC" not in m for m in seen)


def test_prompt_hash_shape():
    h = agent_trace.prompt_hash("x")
    assert re.fullmatch(r"[0-9a-f]{12}", h)


# ---- classifier summary ----------------------------------------------------


class StatsAgent(CategorizationAgent):
    provider = "stub"
    label = "Stub"
    env_var = "STUB_KEY"
    model = "stub-model"

    def __init__(self, stats=None):
        if stats is not None:
            self.last_run_stats = stats

    def is_configured(self):
        return True

    async def classify(self, transactions, categories):
        return [dict(GOOD) for _ in transactions]


async def test_summary_sanitizes_agent_stats(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    stats = {"accepted": 1, "Bad Key": 2, "note": "Tesco", "rows": 99, "score_p50": 0.456, "flag": True}
    monkeypatch.setattr(classifier, "get_active_agent", lambda: StatsAgent(stats))
    await classifier.categorize_transactions(_txns())
    (line,) = [r.getMessage() for r in caplog.records if "event=llm_categorize" in r.getMessage()]
    assert "accepted=1" in line and "score_p50=0.46" in line
    assert "Tesco" not in line and "rows=99" not in line and "Bad Key" not in line and "flag=" not in line
    assert re.search(r" run=[0-9a-f]{12}$", line)


async def test_agent_without_stats_has_plain_summary(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(classifier, "get_active_agent", lambda: StatsAgent())
    await classifier.categorize_transactions(_txns())
    (line,) = [r.getMessage() for r in caplog.records if "event=llm_categorize" in r.getMessage()]
    assert re.match(
        r"^event=llm_categorize provider=stub model=stub-model rows=2 uncategorized=0 ms=\d+\.\d run=[0-9a-f]{12}$",
        line,
    )


# ---- LLM traces ------------------------------------------------------------


async def test_openai_run_writes_batch_and_run_records(monkeypatch, tmp_path, caplog, openai_settings):
    caplog.set_level(logging.INFO)
    d = _set_dir(monkeypatch, tmp_path)

    async def create(**kwargs):
        return _openai_response([GOOD])

    monkeypatch.setattr(llm_mod, "AsyncOpenAI", _fake_openai(create))
    await classifier.categorize_transactions(_txns())

    (line,) = [r.getMessage() for r in caplog.records if "event=llm_categorize" in r.getMessage()]
    m = re.match(
        r"^event=llm_categorize provider=openai model=gpt-test rows=2 uncategorized=1 "
        r"batches=1 failed_batches=0 padded=1 ms=\d+\.\d run=([0-9a-f]{12})$",
        line,
    )
    assert m
    recs = _records(d / "openai.log")
    batch = [r for r in recs if r["stage"] == "batch"]
    run = [r for r in recs if r["stage"] == "run"]
    assert len(batch) == 1 and len(run) == 1
    b = batch[0]
    assert re.fullmatch(r"[0-9a-f]{12}", b["prompt_hash"])
    assert "Tesco" in b["input"]["prompt"]
    assert isinstance(b["output"]["results"], list) and len(b["output"]["results"]) == 1
    assert b["padded"] == 1 and b["status"] == "ok" and b["usage"] is None
    assert b["model"] == "gpt-test" and b["batch"] == "1/1" and b["size"] == 2
    assert run[0]["rows"] == 2 and run[0]["uncategorized"] == 1 and run[0]["status"] == "ok"
    assert b["run_id"] == run[0]["run_id"] == m.group(1)
    assert KEY not in (d / "openai.log").read_text()


async def test_usage_is_normalised(monkeypatch, tmp_path, openai_settings):
    d = _set_dir(monkeypatch, tmp_path)

    async def create(**kwargs):
        return _openai_response([GOOD, GOOD], usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))

    monkeypatch.setattr(llm_mod, "AsyncOpenAI", _fake_openai(create))
    await classifier.categorize_transactions(_txns())
    (b,) = [r for r in _records(d / "openai.log") if r["stage"] == "batch"]
    assert b["usage"] == {"input_tokens": 10, "output_tokens": 5}


async def test_prompt_hash_is_stable_across_runs(monkeypatch, tmp_path, openai_settings):
    d = _set_dir(monkeypatch, tmp_path)

    async def create(**kwargs):
        return _openai_response([GOOD])

    monkeypatch.setattr(llm_mod, "AsyncOpenAI", _fake_openai(create))
    await classifier.categorize_transactions(_txns(1))
    await classifier.categorize_transactions(_txns(2))
    hashes = {r["prompt_hash"] for r in _records(d / "openai.log") if r["stage"] == "batch"}
    assert hashes == {PROMPT_HASH}


async def test_failed_batch_never_leaks_key(monkeypatch, tmp_path, caplog, openai_settings):
    caplog.set_level(logging.INFO)
    d = _set_dir(monkeypatch, tmp_path)

    async def create(**kwargs):
        raise RuntimeError(f"boom {KEY}")

    monkeypatch.setattr(llm_mod, "AsyncOpenAI", _fake_openai(create))
    await classifier.categorize_transactions(_txns())
    (b,) = [r for r in _records(d / "openai.log") if r["stage"] == "batch"]
    assert b["status"] == "RuntimeError" and b["status_code"] is None and b["output"] is None
    assert KEY not in (d / "openai.log").read_bytes().decode()
    (line,) = [r.getMessage() for r in caplog.records if r.getMessage().startswith("event=llm_categorize")]
    assert "failed_batches=1" in line


async def test_anthropic_writes_its_own_file(monkeypatch, tmp_path, openai_settings):
    d = _set_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    text = json.dumps({"results": [GOOD, GOOD]})

    async def create(**kwargs):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(input_tokens=7, output_tokens=3),
        )

    monkeypatch.setattr(llm_mod, "AsyncAnthropic", _fake_anthropic(create))
    await classifier.categorize_transactions(_txns())
    assert (d / "anthropic.log").exists() and not (d / "openai.log").exists()
    (b,) = [r for r in _records(d / "anthropic.log") if r["stage"] == "batch"]
    assert b["usage"] == {"input_tokens": 7, "output_tokens": 3}


async def test_llm_agent_last_run_stats(monkeypatch, openai_settings):
    async def create(**kwargs):
        return _openai_response([GOOD])

    monkeypatch.setattr(llm_mod, "AsyncOpenAI", _fake_openai(create))
    agent = OpenAiAgent()
    await agent.classify(_txns(3), {"G": ["C"]})
    assert agent.last_run_stats == {"batches": 1, "failed_batches": 0, "padded": 2}


async def test_default_off_leaves_no_files(monkeypatch, tmp_path, openai_settings):
    async def create(**kwargs):
        return _openai_response([GOOD])

    monkeypatch.setattr(llm_mod, "AsyncOpenAI", _fake_openai(create))
    await classifier.categorize_transactions(_txns())
    assert list(tmp_path.iterdir()) == []


def test_taxonomy_hash_shape_and_order_sensitivity():
    a = {"A": ["x"], "B": ["y"]}
    h = agent_trace.taxonomy_hash(a)
    assert re.fullmatch(r"[0-9a-f]{12}", h)
    assert agent_trace.taxonomy_hash({"A": ["x"], "B": ["y"]}) == h
    assert agent_trace.taxonomy_hash({"B": ["y"], "A": ["x"]}) != h

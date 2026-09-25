"""LLM categorization events: shape and the no-sensitive-data rule. No network."""

import json
import logging
import re
from types import SimpleNamespace

import pytest

from app.config import settings
from app.services import classifier as categorizer

LOGGERS = {"app.services.agents.llm", "app.services.classifier"}


def _txns(n=2):
    base = [
        {"description": "Tesco", "original_amount": "20.00", "original_currency": "ILS", "bank": "Revolut"},
        {"description": "Weird Merchant", "original_amount": "8.50", "original_currency": "ILS", "bank": "Revolut"},
    ]
    if n <= 2:
        return base[:n]
    return [dict(base[0]) for _ in range(n)]


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


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-DO-NOT-LOG")
    monkeypatch.setattr(settings, "openai_model", "gpt-test")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-DO-NOT-LOG")
    monkeypatch.setattr(settings, "anthropic_model", "claude-test")


def _msgs(caplog, level=None):
    return [
        r.getMessage() for r in caplog.records
        if r.name in LOGGERS and (level is None or r.levelno == level)
    ]


def _assert_private(caplog):
    for r in caplog.records:
        m = r.getMessage()
        for secret in ("DO-NOT-LOG", "Tesco", "Weird Merchant", "20.00", "8.50"):
            assert secret not in m


def _openai_response(results):
    content = json.dumps({"results": results})
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


async def test_openai_success_pads_and_logs(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    async def create(**kwargs):
        return _openai_response([{"general_category": "Household Expenses", "precise_category": "Groceries"}])

    monkeypatch.setattr("app.services.agents.llm.AsyncOpenAI", _fake_openai(create))
    results = await categorizer.categorize_transactions(_txns())
    assert len(results) == 2
    assert results[1]["general_category"] == "Uncategorized"

    msgs = _msgs(caplog, logging.INFO)
    assert any(
        re.match(r"^event=llm_batch provider=openai model=gpt-test batch=1/1 size=2 ok=true padded=1 ms=\d+\.\d$", m)
        for m in msgs
    )
    assert any(
        re.match(
            r"^event=llm_categorize provider=openai model=gpt-test rows=2 uncategorized=1 batches=1 failed_batches=0 padded=1 ms=\d+\.\d run=[0-9a-f]{12}$", m
        )
        for m in msgs
    )
    _assert_private(caplog)


async def test_batching_logs_each_batch(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    async def create(**kwargs):
        n = 30 if "30." in kwargs["messages"][0]["content"] else 1
        return _openai_response([{"general_category": "Household Expenses", "precise_category": "Groceries"}] * n)

    monkeypatch.setattr("app.services.agents.llm.AsyncOpenAI", _fake_openai(create))
    await categorizer.categorize_transactions(_txns(31))
    msgs = _msgs(caplog, logging.INFO)
    assert any(" batch=1/2 size=30 " in m for m in msgs)
    assert any(" batch=2/2 size=1 " in m for m in msgs)


async def test_openai_failure_logs_class_only(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    async def create(**kwargs):
        raise RuntimeError("boom sk-test-DO-NOT-LOG")

    monkeypatch.setattr("app.services.agents.llm.AsyncOpenAI", _fake_openai(create))
    results = await categorizer.categorize_transactions(_txns())
    assert all(r["general_category"] == "Uncategorized" for r in results)
    assert any(
        re.match(
            r"^event=llm_batch provider=openai model=gpt-test batch=1/1 size=2 ok=false "
            r"fallback=uncategorized error=RuntimeError status_code=- ms=\d+\.\d$",
            m,
        )
        for m in _msgs(caplog, logging.ERROR)
    )
    _assert_private(caplog)


async def test_status_code_is_logged(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    class AuthError(Exception):
        status_code = 401

    async def create(**kwargs):
        raise AuthError("nope")

    monkeypatch.setattr("app.services.agents.llm.AsyncOpenAI", _fake_openai(create))
    await categorizer.categorize_transactions(_txns())
    assert any("error=AuthError status_code=401" in m for m in _msgs(caplog, logging.ERROR))


async def test_anthropic_failure_logs(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(settings, "ai_provider", "anthropic")

    async def create(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.services.agents.llm.AsyncAnthropic", _fake_anthropic(create))
    await categorizer.categorize_transactions(_txns())
    errors = _msgs(caplog, logging.ERROR)
    assert any("event=llm_batch provider=anthropic model=claude-test" in m and "ok=false" in m for m in errors)
    _assert_private(caplog)


async def test_no_api_key_logs_skip(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(settings, "openai_api_key", "")
    results = await categorizer.categorize_transactions(_txns())
    assert all(r["general_category"] == "Uncategorized" for r in results)
    assert any(
        re.match(r"^event=llm_categorize provider=openai model=gpt-test rows=2 ok=false skipped=no_api_key run=[0-9a-f]{12}$", m)
        for m in _msgs(caplog, logging.WARNING)
    )
    _assert_private(caplog)


async def test_anthropic_success_logs_batch(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    text = json.dumps({"results": [{"general_category": "Household Expenses", "precise_category": "Groceries"}] * 2})

    async def create(**kwargs):
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])

    monkeypatch.setattr("app.services.agents.llm.AsyncAnthropic", _fake_anthropic(create))
    await categorizer.categorize_transactions(_txns())
    assert any(
        re.match(r"^event=llm_batch provider=anthropic model=claude-test batch=1/1 size=2 ok=true padded=0 ms=", m)
        for m in _msgs(caplog, logging.INFO)
    )

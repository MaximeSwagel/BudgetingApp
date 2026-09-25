import json
from types import SimpleNamespace

import pytest

from app.config import settings
from app.services.agents import llm as llm_mod
from app.services.agents.base import UNCATEGORIZED
from app.services.agents.llm import AnthropicAgent, OpenAiAgent

GOOD = {"general_category": "Household Expenses", "precise_category": "Groceries"}


def txns(n):
    return [
        {"description": f"t{i}", "original_amount": "1.00", "original_currency": "ILS", "bank": "Revolut"}
        for i in range(n)
    ]


def fake_openai(replies, calls):
    async def create(**kwargs):
        calls.append(kwargs)
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])

    def factory(api_key):
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    return factory


def fake_anthropic(replies, calls):
    async def create(**kwargs):
        calls.append(kwargs)
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=reply)])

    def factory(api_key):
        return SimpleNamespace(messages=SimpleNamespace(create=create))

    return factory


@pytest.mark.asyncio
async def test_openai_batches_of_30(monkeypatch):
    calls = []
    replies = [json.dumps({"results": [GOOD] * 30}), json.dumps({"results": [GOOD] * 5})]
    monkeypatch.setattr(llm_mod, "AsyncOpenAI", fake_openai(replies, calls))

    out = await OpenAiAgent().classify(txns(35))

    assert len(calls) == 2
    assert out == [GOOD] * 35
    assert calls[0]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_openai_accepts_bare_array_and_odd_key(monkeypatch):
    calls = []
    replies = [json.dumps([GOOD, GOOD]), json.dumps({"whatever": [GOOD]})]
    monkeypatch.setattr(llm_mod, "AsyncOpenAI", fake_openai(replies, calls))

    assert await OpenAiAgent().classify(txns(2)) == [GOOD, GOOD]
    assert await OpenAiAgent().classify(txns(1)) == [GOOD]


@pytest.mark.asyncio
async def test_openai_short_reply_is_padded(monkeypatch):
    monkeypatch.setattr(llm_mod, "AsyncOpenAI", fake_openai([json.dumps({"results": [GOOD]})], []))

    out = await OpenAiAgent().classify(txns(3))

    assert out == [GOOD, UNCATEGORIZED, UNCATEGORIZED]


@pytest.mark.asyncio
async def test_openai_exception_gives_uncategorized_for_batch(monkeypatch):
    monkeypatch.setattr(llm_mod, "AsyncOpenAI", fake_openai([RuntimeError("boom")], []))

    assert await OpenAiAgent().classify(txns(2)) == [UNCATEGORIZED, UNCATEGORIZED]


@pytest.mark.asyncio
async def test_anthropic_uses_json_schema_and_pads(monkeypatch):
    calls = []
    monkeypatch.setattr(llm_mod, "AsyncAnthropic", fake_anthropic([json.dumps({"results": [GOOD]})], calls))

    out = await AnthropicAgent().classify(txns(2))

    assert out == [GOOD, UNCATEGORIZED]
    assert calls[0]["output_config"]["format"]["type"] == "json_schema"


@pytest.mark.asyncio
async def test_anthropic_exception_gives_uncategorized(monkeypatch):
    monkeypatch.setattr(llm_mod, "AsyncAnthropic", fake_anthropic([RuntimeError("boom")], []))

    assert await AnthropicAgent().classify(txns(2)) == [UNCATEGORIZED, UNCATEGORIZED]


def test_is_configured_reads_settings_at_call_time(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "k")

    assert OpenAiAgent().is_configured() is False
    assert AnthropicAgent().is_configured() is True
    assert OpenAiAgent.env_var == "OPENAI_API_KEY"
    assert AnthropicAgent.env_var == "ANTHROPIC_API_KEY"

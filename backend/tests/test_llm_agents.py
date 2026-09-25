import hashlib
import json
import logging
from types import SimpleNamespace

import pytest

from app import agent_trace
from app.config import settings
from app.main import SEED_CATEGORIES
from app.services.agents import llm as llm_mod
from app.services.agents.base import UNCATEGORIZED
from app.services.agents.llm import AnthropicAgent, OpenAiAgent

GOOD = {"general_category": "Household Expenses", "precise_category": "Groceries"}


PRE_CHANGE_SEED_PROMPT_SHA256 = "f2469f5c37c7c934e8c517fa80822815a4f72f2db8f811fcdd40544eefe3da58"
TAXONOMY = {g: list(c) for g, c in SEED_CATEGORIES.items()}


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

    out = await OpenAiAgent().classify(txns(35), TAXONOMY)

    assert len(calls) == 2
    assert out == [GOOD] * 35
    assert calls[0]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_openai_accepts_bare_array_and_odd_key(monkeypatch):
    calls = []
    replies = [json.dumps([GOOD, GOOD]), json.dumps({"whatever": [GOOD]})]
    monkeypatch.setattr(llm_mod, "AsyncOpenAI", fake_openai(replies, calls))

    assert await OpenAiAgent().classify(txns(2), TAXONOMY) == [GOOD, GOOD]
    assert await OpenAiAgent().classify(txns(1), TAXONOMY) == [GOOD]


@pytest.mark.asyncio
async def test_openai_short_reply_is_padded(monkeypatch):
    monkeypatch.setattr(llm_mod, "AsyncOpenAI", fake_openai([json.dumps({"results": [GOOD]})], []))

    out = await OpenAiAgent().classify(txns(3), TAXONOMY)

    assert out == [GOOD, UNCATEGORIZED, UNCATEGORIZED]


@pytest.mark.asyncio
async def test_openai_exception_gives_uncategorized_for_batch(monkeypatch):
    monkeypatch.setattr(llm_mod, "AsyncOpenAI", fake_openai([RuntimeError("boom")], []))

    assert await OpenAiAgent().classify(txns(2), TAXONOMY) == [UNCATEGORIZED, UNCATEGORIZED]


@pytest.mark.asyncio
async def test_anthropic_uses_json_schema_and_pads(monkeypatch):
    calls = []
    monkeypatch.setattr(llm_mod, "AsyncAnthropic", fake_anthropic([json.dumps({"results": [GOOD]})], calls))

    out = await AnthropicAgent().classify(txns(2), TAXONOMY)

    assert out == [GOOD, UNCATEGORIZED]
    assert calls[0]["output_config"]["format"]["type"] == "json_schema"


@pytest.mark.asyncio
async def test_anthropic_exception_gives_uncategorized(monkeypatch):
    monkeypatch.setattr(llm_mod, "AsyncAnthropic", fake_anthropic([RuntimeError("boom")], []))

    assert await AnthropicAgent().classify(txns(2), TAXONOMY) == [UNCATEGORIZED, UNCATEGORIZED]


def test_is_configured_reads_settings_at_call_time(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "k")

    assert OpenAiAgent().is_configured() is False
    assert AnthropicAgent().is_configured() is True
    assert OpenAiAgent.env_var == "OPENAI_API_KEY"
    assert AnthropicAgent.env_var == "ANTHROPIC_API_KEY"


def _content(calls):
    return calls[0]["messages"][0]["content"]


def test_seed_prompt_is_byte_identical_to_pre_change():
    prompt = llm_mod._build_prompt(txns(2), TAXONOMY)
    assert hashlib.sha256(prompt.encode()).hexdigest() == PRE_CHANGE_SEED_PROMPT_SHA256


@pytest.mark.asyncio
async def test_prompt_lists_passed_groups_in_order_and_skips_empty(monkeypatch):
    calls = []
    monkeypatch.setattr(llm_mod, "AsyncOpenAI", fake_openai([json.dumps({"results": [GOOD]})], calls))
    tax = {"Pets": ["Pet Food", "Vet"], "Household Expenses": ["Supermarket"], "Hollow": []}

    await OpenAiAgent().classify(txns(1), tax)

    text = _content(calls)
    assert text.index("- Pets: Pet Food, Vet") < text.index("- Household Expenses: Supermarket")
    assert "Hollow" not in text


@pytest.mark.asyncio
@pytest.mark.parametrize("tax", [{}, {"Empty": []}])
async def test_empty_taxonomy_makes_no_call(monkeypatch, caplog, tax):
    caplog.set_level(logging.INFO)
    calls = []
    monkeypatch.setattr(llm_mod, "AsyncOpenAI", fake_openai([], calls))

    out = await OpenAiAgent().classify(txns(2), tax)

    assert out == [UNCATEGORIZED, UNCATEGORIZED] and calls == []
    warn = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("event=agent_taxonomy provider=openai ok=false reason=empty" in r.getMessage() for r in warn)


@pytest.mark.asyncio
async def test_batch_trace_carries_taxonomy_hash(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "agent_log_dir", str(tmp_path))
    monkeypatch.setattr(settings, "openai_api_key", "k")
    other = {"Pets": ["Vet"]}
    for tax in (TAXONOMY, other):
        monkeypatch.setattr(llm_mod, "AsyncOpenAI", fake_openai([json.dumps({"results": [GOOD]})], []))
        await OpenAiAgent().classify(txns(1), tax)
    recs = [json.loads(line) for line in (tmp_path / "openai.log").read_text().splitlines()]
    a, b = [r for r in recs if r["stage"] == "batch"]
    assert a["taxonomy_hash"] == agent_trace.taxonomy_hash(TAXONOMY)
    assert b["taxonomy_hash"] == agent_trace.taxonomy_hash(other)
    assert a["taxonomy_hash"] != b["taxonomy_hash"]
    assert a["prompt_hash"] == b["prompt_hash"] == llm_mod.PROMPT_HASH

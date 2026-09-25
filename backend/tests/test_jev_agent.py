import asyncio
import json

import httpx
import pytest

from app.services.agents import jev as jev_mod
from app.services.agents.base import CATEGORY_HIERARCHY, UNCATEGORIZED
from app.services.agents.jev import JevAgent

GROUPS = list(CATEGORY_HIERARCHY)
GROCERY_GROUP = "Household Expenses"


def txn(desc, amount="10.00"):
    return {"description": desc, "original_amount": amount, "original_currency": "ILS", "bank": "Revolut"}


def slug_for(criteria, name):
    """Find the option key whose description mentions the wanted name."""
    for key, desc in criteria.items():
        if desc.startswith(f"{name}:") or desc == name:
            return key
    raise AssertionError(f"{name} not offered in {criteria}")


def answer(qid, choice, confidence, criteria):
    probs = {k: (confidence if k == choice else 0.0) for k in criteria}
    return {"answers": {qid: {"type": "choice", "choice": choice, "confidence": confidence, "probabilities": probs}}}


def make_agent(handler, **kw):
    kw.setdefault("api_key", "sk-test")
    kw.setdefault("threshold", 0.6)
    return JevAgent(transport=httpx.MockTransport(handler), **kw)


def happy_handler(group_conf=0.9, cat_conf=0.9, log=None):
    async def handler(request):
        body = json.loads(request.content)
        (qid, q), = body["questions"].items()
        if log is not None:
            log.append((qid, body["state"]["description"]))
        if qid == "group":
            return httpx.Response(200, json=answer(qid, slug_for(q["criteria"], GROCERY_GROUP), group_conf, q["criteria"]))
        # criteria descriptions for categories are the plain names
        key = next(k for k, d in q["criteria"].items() if d == "Groceries" or k == "groceries")
        return httpx.Response(200, json=answer(qid, key, cat_conf, q["criteria"]))

    return handler


@pytest.mark.asyncio
async def test_two_step_classification():
    log = []
    agent = make_agent(happy_handler(log=log))

    out = await agent.classify([txn("Tesco")])

    assert out[0]["general_category"] == GROCERY_GROUP
    assert out[0]["precise_category"] == "Groceries"
    assert out[0]["confidence"] == pytest.approx(0.9)
    assert [q for q, _ in log] == ["group", "category"]


@pytest.mark.asyncio
async def test_group_question_offers_groups_plus_other_and_category_only_chosen_group():
    captured = {}

    async def handler(request):
        body = json.loads(request.content)
        (qid, q), = body["questions"].items()
        captured[qid] = q
        if qid == "group":
            return httpx.Response(200, json=answer(qid, slug_for(q["criteria"], GROCERY_GROUP), 0.9, q["criteria"]))
        key = next(iter(q["criteria"]))
        return httpx.Response(200, json=answer(qid, key, 0.9, q["criteria"]))

    await make_agent(handler).classify([txn("Tesco")])

    assert len(captured["group"]["criteria"]) == len(GROUPS) + 1
    assert "other" in captured["group"]["criteria"]
    assert len(captured["category"]["criteria"]) == len(CATEGORY_HIERARCHY[GROCERY_GROUP])


@pytest.mark.asyncio
async def test_state_carries_description_amount_currency_bank():
    seen = {}

    async def handler(request):
        body = json.loads(request.content)
        seen.update(body["state"])
        (qid, q), = body["questions"].items()
        return httpx.Response(200, json=answer(qid, "other", 0.99, q["criteria"]))

    await make_agent(handler).classify([txn("Tesco", "12.50")])

    assert seen == {"description": "Tesco", "amount": "12.50", "currency": "ILS", "bank": "Revolut"}


@pytest.mark.asyncio
async def test_low_group_confidence_is_uncategorized_and_skips_step_two():
    log = []
    out = await make_agent(happy_handler(group_conf=0.4, log=log)).classify([txn("Tesco")])

    assert out[0] == UNCATEGORIZED
    assert [q for q, _ in log] == ["group"]


@pytest.mark.asyncio
async def test_low_category_confidence_is_uncategorized():
    out = await make_agent(happy_handler(cat_conf=0.5)).classify([txn("Tesco")])

    assert out[0] == UNCATEGORIZED


@pytest.mark.asyncio
async def test_other_group_is_uncategorized_without_step_two():
    log = []

    async def handler(request):
        body = json.loads(request.content)
        (qid, q), = body["questions"].items()
        log.append(qid)
        return httpx.Response(200, json=answer(qid, "other", 0.99, q["criteria"]))

    out = await make_agent(handler).classify([txn("Salary")])

    assert out[0] == UNCATEGORIZED
    assert log == ["group"]


@pytest.mark.asyncio
async def test_score_falls_back_to_probability_when_confidence_absent():
    async def handler(request):
        body = json.loads(request.content)
        (qid, q), = body["questions"].items()
        choice = slug_for(q["criteria"], GROCERY_GROUP) if qid == "group" else next(iter(q["criteria"]))
        probs = {k: (0.8 if k == choice else 0.0) for k in q["criteria"]}
        return httpx.Response(
            200, json={"answers": {qid: {"type": "choice", "choice": choice, "probabilities": probs}}}
        )

    out = await make_agent(handler).classify([txn("Tesco")])

    assert out[0]["general_category"] == GROCERY_GROUP


@pytest.mark.asyncio
async def test_single_line_failure_is_isolated():
    async def handler(request):
        body = json.loads(request.content)
        if body["state"]["description"] == "Boom":
            return httpx.Response(400, text="bad")
        return await happy_handler()(request)

    out = await make_agent(handler).classify([txn("Tesco"), txn("Boom"), txn("Tesco")])

    assert out[0]["general_category"] == GROCERY_GROUP
    assert out[1] == UNCATEGORIZED
    assert out[2]["general_category"] == GROCERY_GROUP


@pytest.mark.asyncio
async def test_output_order_matches_input_when_later_lines_finish_first():
    async def handler(request):
        body = json.loads(request.content)
        desc = body["state"]["description"]
        await asyncio.sleep(0.05 if desc == "slow" else 0)
        (qid, q), = body["questions"].items()
        if desc == "slow":
            return httpx.Response(200, json=answer(qid, "other", 0.99, q["criteria"]))
        return await happy_handler()(request)

    out = await make_agent(handler).classify([txn("slow"), txn("fast"), txn("fast")])

    assert out[0] == UNCATEGORIZED
    assert out[1]["general_category"] == GROCERY_GROUP
    assert out[2]["general_category"] == GROCERY_GROUP
    assert len(out) == 3


@pytest.mark.asyncio
async def test_concurrency_is_capped(monkeypatch):
    monkeypatch.setattr(jev_mod, "JEV_MAX_CONCURRENCY", 2)
    state = {"now": 0, "peak": 0}

    async def handler(request):
        state["now"] += 1
        state["peak"] = max(state["peak"], state["now"])
        await asyncio.sleep(0.01)
        state["now"] -= 1
        return await happy_handler()(request)

    await make_agent(handler).classify([txn(f"t{i}") for i in range(6)])

    assert state["peak"] == 2


@pytest.mark.asyncio
async def test_auth_error_short_circuits_remaining_lines(monkeypatch):
    monkeypatch.setattr(jev_mod, "JEV_MAX_CONCURRENCY", 1)
    calls = []

    async def handler(request):
        calls.append(1)
        return httpx.Response(401, text="no")

    out = await make_agent(handler).classify([txn(f"t{i}") for i in range(5)])

    assert out == [UNCATEGORIZED] * 5
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_empty_input_makes_no_requests():
    async def handler(request):
        raise AssertionError("no HTTP expected")

    assert await make_agent(handler).classify([]) == []


def test_is_configured_follows_key():
    assert JevAgent(api_key="k").is_configured() is True
    assert JevAgent(api_key="").is_configured() is False

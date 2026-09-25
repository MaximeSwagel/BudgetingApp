import asyncio
import json
import logging
import re

import httpx
import pytest

from app import agent_trace
from app.config import settings
from app.services import classifier
from app.services import openrouter_client as oc
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


def answer(qid, choice, confidence, criteria, cost=None):
    probs = {k: (confidence if k == choice else 0.0) for k in criteria}
    body = {"answers": {qid: {"type": "choice", "choice": choice, "confidence": confidence, "probabilities": probs}}}
    if cost is not None:
        body["usage"] = {"cost": cost}
    return body


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


# ---- trace records and reason stats ----------------------------------------

KEY = "sk-SENTINEL-JEV"
MIXED = [txn("Tesco"), txn("Salary"), txn("Low"), txn("CatLow"), txn("Boom")]


def mixed_handler(cost=None):
    async def handler(request):
        body = json.loads(request.content)
        (qid, q), = body["questions"].items()
        desc = body["state"]["description"]
        if desc == "Boom":
            return httpx.Response(400, text="bad")
        criteria = q["criteria"]
        if qid == "group":
            if desc == "Salary":
                return httpx.Response(200, json=answer(qid, "other", 0.99, criteria, cost))
            conf = 0.4 if desc == "Low" else 0.9
            return httpx.Response(200, json=answer(qid, slug_for(criteria, GROCERY_GROUP), conf, criteria, cost))
        key = next(k for k, d in criteria.items() if d == "Groceries")
        return httpx.Response(200, json=answer(qid, key, 0.5 if desc == "CatLow" else 0.9, criteria, cost))

    return handler


def trace_to(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "agent_log_dir", str(tmp_path / "agent-logs"))
    return tmp_path / "agent-logs" / "openrouter.log"


def records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def by_stage(recs, stage, desc=None):
    return [
        r for r in recs
        if r["stage"] == stage and (desc is None or r["input"]["state"]["description"] == desc)
    ]


STATS_KEYS = [
    "accepted", "group_other", "group_low", "category_low", "errors", "auth",
    "group_score_min", "group_score_p50", "group_score_max",
    "cat_score_min", "cat_score_p50", "cat_score_max",
]


@pytest.mark.asyncio
async def test_mixed_run_results_and_stats():
    agent = make_agent(mixed_handler())

    out = await agent.classify(MIXED)

    assert [r["general_category"] for r in out] == [GROCERY_GROUP] + ["Uncategorized"] * 4
    stats = agent.last_run_stats
    assert list(stats) == STATS_KEYS
    expected = dict(
        accepted=1, group_other=1, group_low=1, category_low=1, errors=1, auth=0,
        group_score_min=0.4, group_score_p50=0.9, group_score_max=0.99,
        cat_score_min=0.5, cat_score_p50=0.7, cat_score_max=0.9,
    )
    assert stats == pytest.approx(expected)


@pytest.mark.asyncio
async def test_auth_failure_stats_and_records(monkeypatch, tmp_path):
    path = trace_to(monkeypatch, tmp_path)
    monkeypatch.setattr(jev_mod, "JEV_MAX_CONCURRENCY", 1)

    async def handler(request):
        return httpx.Response(401, text="nope")

    agent = make_agent(handler)
    await agent.classify([txn(f"t{i}") for i in range(5)])

    assert agent.last_run_stats == dict(accepted=0, group_other=0, group_low=0, category_low=0, errors=0, auth=5)
    recs = records(path)
    (call,) = by_stage(recs, "group")
    assert call["status"] == "DecisionsAuthError" and call["status_code"] == 401 and call["decision"] == "auth"
    lines = by_stage(recs, "line")
    assert len(lines) == 5 and {r["decision"] for r in lines} == {"auth"}


@pytest.mark.asyncio
async def test_trace_records_for_accepted_line(monkeypatch, tmp_path):
    path = trace_to(monkeypatch, tmp_path)
    agent = make_agent(mixed_handler(cost=0.00002))

    with agent_trace.trace_run() as run_id:
        await agent.classify([txn("Tesco")])

    recs = records(path)
    assert all(r["provider"] == "openrouter" and r["model"] == "~typesafe/jev-latest" for r in recs)
    assert all(r["run_id"] == run_id for r in recs)
    (group,) = by_stage(recs, "group")
    assert group["input"]["state"] == {
        "description": "Tesco", "amount": "10.00", "currency": "ILS", "bank": "Revolut",
    }
    assert len(group["input"]["options"]) == len(GROUPS) + 1 and "other" in group["input"]["options"]
    top = group["output"]["top"]
    assert 1 <= len(top) <= 3 and [p for _, p in top] == sorted((p for _, p in top), reverse=True)
    assert group["output"]["choice"] == top[0][0] and group["output"]["confidence"] == 0.9
    assert isinstance(group["ms"], float) and group["ms"] >= 0 and group["queue_ms"] >= 0
    assert group["attempts"] == 1 and group["status"] == "ok" and group["status_code"] is None
    assert group["decision"] == "accepted" and group["threshold"] == 0.6 and group["cost"] == 0.00002
    (cat,) = by_stage(recs, "category")
    assert cat["input"]["options"] == list(jev_mod.CATEGORY_SLUGS[GROCERY_GROUP])
    assert cat["decision"] == "accepted" and cat["queue_ms"] == 0.0
    (line,) = by_stage(recs, "line")
    assert line["group"] == GROCERY_GROUP and line["category"] == "Groceries"
    assert line["decision"] == "accepted" and isinstance(line["total_ms"], float)
    assert line["cost"] == pytest.approx(0.00004)


@pytest.mark.asyncio
async def test_cost_is_null_when_absent(monkeypatch, tmp_path):
    path = trace_to(monkeypatch, tmp_path)
    await make_agent(mixed_handler()).classify([txn("Tesco")])
    recs = records(path)
    assert all(r["cost"] is None for r in recs)


@pytest.mark.asyncio
async def test_retry_is_visible_as_attempts(monkeypatch, tmp_path):
    path = trace_to(monkeypatch, tmp_path)
    monkeypatch.setattr(oc, "RETRY_BACKOFF_SECONDS", 0)
    calls = []
    inner = mixed_handler()

    async def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return await inner(request)

    await make_agent(handler).classify([txn("Tesco")])
    (group,) = by_stage(records(path), "group")
    assert group["attempts"] == 2


@pytest.mark.asyncio
async def test_error_line_and_decisions(monkeypatch, tmp_path):
    path = trace_to(monkeypatch, tmp_path)
    await make_agent(mixed_handler()).classify(MIXED)
    recs = records(path)
    (boom,) = by_stage(recs, "group", "Boom")
    assert boom["status"] == "DecisionsError" and boom["status_code"] == 400
    assert boom["output"] is None and boom["decision"] == "error"
    decisions = {r["input"]["state"]["description"]: r["decision"] for r in by_stage(recs, "line")}
    assert decisions == {
        "Tesco": "accepted", "Salary": "other", "Low": "group_low", "CatLow": "category_low", "Boom": "error",
    }
    assert by_stage(recs, "group", "Salary")[0]["decision"] == "other"
    assert by_stage(recs, "group", "Low")[0]["decision"] == "group_low"
    assert by_stage(recs, "category", "CatLow")[0]["decision"] == "category_low"


@pytest.mark.parametrize("status", [500, 401])
@pytest.mark.asyncio
async def test_api_key_never_reaches_trace_file(monkeypatch, tmp_path, status):
    path = trace_to(monkeypatch, tmp_path)
    monkeypatch.setattr(oc, "RETRY_BACKOFF_SECONDS", 0)

    async def handler(request):
        return httpx.Response(status, text=f"echo {KEY}")

    await make_agent(handler, api_key=KEY).classify([txn("Tesco")])
    assert path.exists()
    assert KEY not in path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_queue_ms_reflects_semaphore_wait(monkeypatch, tmp_path):
    path = trace_to(monkeypatch, tmp_path)
    monkeypatch.setattr(jev_mod, "JEV_MAX_CONCURRENCY", 1)
    inner = mixed_handler()

    async def handler(request):
        await asyncio.sleep(0.02)
        return await inner(request)

    await make_agent(handler).classify([txn("Tesco"), txn("Tesco"), txn("Tesco")])
    assert any(r["queue_ms"] > 0 for r in by_stage(records(path), "line"))


@pytest.mark.asyncio
async def test_summary_line_carries_reasons_and_run(monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO)
    agent = make_agent(mixed_handler())
    monkeypatch.setattr(classifier, "get_active_agent", lambda: agent)

    await classifier.categorize_transactions(MIXED)

    msgs = [r.getMessage() for r in caplog.records]
    (line,) = [m for m in msgs if m.startswith("event=llm_categorize")]
    assert re.search(
        r"rows=5 uncategorized=4 accepted=1 group_other=1 group_low=1 category_low=1 errors=1 auth=0 "
        r"group_score_min=0.40 group_score_p50=0.90 group_score_max=0.99 "
        r"cat_score_min=0.50 cat_score_p50=0.70 cat_score_max=0.90 ms=\d+\.\d run=[0-9a-f]{12}$",
        line,
    )
    for m in msgs:
        for secret in ("Tesco", "Salary", "10.00", "sk-test"):
            assert secret not in m

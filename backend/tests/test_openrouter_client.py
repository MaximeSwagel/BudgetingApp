import json

import httpx
import pytest

from app.services import openrouter_client as oc
from app.services.openrouter_client import (
    DECISIONS_URL,
    JEV_MODEL,
    DecisionsAuthError,
    DecisionsError,
    decide_choice,
)

CRITERIA = {"a": "Option A", "b": "Option B"}


def ok_body(choice="a", confidence=0.9, probabilities=None, qid="q"):
    answer = {"type": "choice", "choice": choice, "probabilities": probabilities or {"a": 0.9, "b": 0.1}}
    if confidence is not None:
        answer["confidence"] = confidence
    return {"id": "x", "answers": {qid: answer}, "usage": {"input_tokens": 5, "output_tokens": 1, "cost": 0.00002}}


async def call(handler, api_key="sk-secret-key"):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await decide_choice(
            client, api_key=api_key, state={"description": "x"}, question_id="q",
            instructions="Pick", criteria=CRITERIA,
        )


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(oc, "RETRY_BACKOFF_SECONDS", 0)


@pytest.mark.asyncio
async def test_builds_request_and_parses_answer():
    seen = {}

    async def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ok_body())

    answer = await call(handler)

    assert seen["url"] == DECISIONS_URL
    assert seen["auth"] == "Bearer sk-secret-key"
    assert seen["body"] == {
        "model": JEV_MODEL,
        "state": {"description": "x"},
        "questions": {"q": {"type": "choice", "instructions": "Pick", "criteria": CRITERIA}},
    }
    assert answer.choice == "a"
    assert answer.confidence == 0.9
    assert answer.probabilities == {"a": 0.9, "b": 0.1}
    assert answer.cost == 0.00002


@pytest.mark.asyncio
async def test_confidence_may_be_absent():
    async def handler(request):
        return httpx.Response(200, json=ok_body(confidence=None))

    assert (await call(handler)).confidence is None


@pytest.mark.asyncio
async def test_retries_429_then_succeeds():
    calls = []

    async def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=ok_body())

    assert (await call(handler)).choice == "a"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_gives_up_after_max_retries():
    calls = []

    async def handler(request):
        calls.append(1)
        return httpx.Response(503, text="down")

    with pytest.raises(DecisionsError):
        await call(handler)
    assert len(calls) == oc.MAX_RETRIES + 1


@pytest.mark.asyncio
async def test_timeout_is_retried():
    calls = []

    async def handler(request):
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, json=ok_body())

    assert (await call(handler)).choice == "a"
    assert len(calls) == 3


@pytest.mark.parametrize("status", [401, 402, 403])
@pytest.mark.asyncio
async def test_auth_errors_do_not_retry(status):
    calls = []

    async def handler(request):
        calls.append(1)
        return httpx.Response(status, text="nope")

    with pytest.raises(DecisionsAuthError):
        await call(handler)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_other_4xx_does_not_retry():
    calls = []

    async def handler(request):
        calls.append(1)
        return httpx.Response(400, text="bad")

    with pytest.raises(DecisionsError) as exc:
        await call(handler)
    assert not isinstance(exc.value, DecisionsAuthError)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "body",
    [
        {"answers": {}},
        {},
        {"answers": {"q": {"type": "noul", "choice": "a"}}},
        {"answers": {"q": {"type": "choice", "choice": "zzz", "probabilities": {}}}},
        {"answers": {"q": {"type": "choice", "choice": "a", "probabilities": {"a": "high"}}}},
        {"answers": {"q": {"type": "choice", "choice": "a", "confidence": "x", "probabilities": {"a": 1}}}},
    ],
)
@pytest.mark.asyncio
async def test_malformed_body_raises(body):
    async def handler(request):
        return httpx.Response(200, json=body)

    with pytest.raises(DecisionsError):
        await call(handler)


@pytest.mark.asyncio
async def test_non_json_body_raises():
    async def handler(request):
        return httpx.Response(200, text="<html>")

    with pytest.raises(DecisionsError):
        await call(handler)


@pytest.mark.asyncio
async def test_key_never_in_error_message():
    async def handler(request):
        return httpx.Response(500, text="server said sk-secret-key")

    with pytest.raises(DecisionsError) as exc:
        await call(handler)
    assert "sk-secret-key" not in str(exc.value)

    async def auth(request):
        return httpx.Response(401, text="bad key sk-secret-key")

    with pytest.raises(DecisionsAuthError) as exc:
        await call(auth)
    assert "sk-secret-key" not in str(exc.value)

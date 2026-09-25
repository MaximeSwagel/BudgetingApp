"""OpenRouter Decisions API client. The endpoint is alpha, so every piece of
wire-format knowledge (URL, model, request/response shape) lives only here."""

import asyncio
import random
from dataclasses import dataclass

import httpx

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
JEV_MODEL = "~typesafe/jev-latest"

RETRYABLE_STATUS = {429, 500, 502, 503, 504, 524, 529}
AUTH_STATUS = {401, 402, 403}
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 0.5
MAX_BACKOFF_SECONDS = 8.0


class DecisionsError(Exception):
    pass


class DecisionsAuthError(DecisionsError):
    pass


@dataclass(frozen=True)
class ChoiceAnswer:
    choice: str
    confidence: float | None
    probabilities: dict[str, float]
    cost: float | None


def _delay(attempt: int, response: httpx.Response | None) -> float:
    if response is not None:
        try:
            return min(max(float(response.headers["Retry-After"]), 0.0), MAX_BACKOFF_SECONDS)
        except (KeyError, ValueError):
            pass
    backoff = RETRY_BACKOFF_SECONDS * (2 ** attempt)
    return min(backoff + random.uniform(0, backoff / 2), MAX_BACKOFF_SECONDS)


def _snippet(response: httpx.Response, api_key: str) -> str:
    # Never include request headers; also scrub the key in case the server echoes it.
    text = response.text.replace(api_key, "***") if api_key else response.text
    return text[:200].replace("\n", " ")


def _parse_choice(data, question_id: str, criteria: dict[str, str]) -> ChoiceAnswer:
    try:
        answer = data["answers"][question_id]
        if answer["type"] != "choice":
            raise DecisionsError("answer is not a choice")
        choice = answer["choice"]
        if choice not in criteria:
            raise DecisionsError("choice is not one of the offered options")
        raw_conf = answer.get("confidence")
        confidence = None if raw_conf is None else float(raw_conf)
        probabilities = {str(k): float(v) for k, v in (answer.get("probabilities") or {}).items()}
        raw_cost = (data.get("usage") or {}).get("cost")
        cost = None if raw_cost is None else float(raw_cost)
    except DecisionsError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise DecisionsError(f"malformed decisions response ({type(e).__name__})") from None
    return ChoiceAnswer(choice=choice, confidence=confidence, probabilities=probabilities, cost=cost)


async def decide_choice(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    state: dict,
    question_id: str,
    instructions: str,
    criteria: dict[str, str],
) -> ChoiceAnswer:
    body = {
        "model": JEV_MODEL,
        "state": state,
        "questions": {
            question_id: {"type": "choice", "instructions": instructions, "criteria": criteria},
        },
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    last_error = "no attempt made"
    for attempt in range(MAX_RETRIES + 1):
        response = None
        try:
            response = await client.post(DECISIONS_URL, json=body, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last_error = type(e).__name__
        else:
            if response.status_code in AUTH_STATUS:
                raise DecisionsAuthError(f"OpenRouter rejected the request ({response.status_code}): {_snippet(response, api_key)}")
            if response.status_code in RETRYABLE_STATUS:
                last_error = f"status {response.status_code}: {_snippet(response, api_key)}"
            elif response.status_code >= 400:
                raise DecisionsError(f"decisions request failed ({response.status_code}): {_snippet(response, api_key)}")
            else:
                try:
                    data = response.json()
                except ValueError:
                    raise DecisionsError("decisions response was not JSON") from None
                return _parse_choice(data, question_id, criteria)

        if attempt < MAX_RETRIES:
            await asyncio.sleep(_delay(attempt, response))

    raise DecisionsError(f"decisions request failed after retries ({last_error})")

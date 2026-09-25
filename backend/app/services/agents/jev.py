import asyncio
import logging
import re
import statistics
import time

import httpx

from app import agent_trace
from app.config import settings
from app.observability import elapsed_ms, log_event
from app.services.agents.base import CATEGORY_HIERARCHY, UNCATEGORIZED, CategorizationAgent
from app.services.openrouter_client import JEV_MODEL, DecisionsAuthError, DecisionsError, decide_choice

logger = logging.getLogger(__name__)

JEV_MAX_CONCURRENCY = 8
JEV_REQUEST_TIMEOUT_SECONDS = 20.0
OTHER_OPTION = "other"

GROUP_INSTRUCTIONS = (
    "Which budget group does this personal bank-statement transaction belong to? "
    "Negative amounts are money spent."
)
CATEGORY_INSTRUCTIONS = (
    "Which sub-category of the {group} budget group fits this personal bank-statement "
    "transaction best? Negative amounts are money spent."
)
OTHER_DESCRIPTION = (
    "Income or salary, refunds, transfers between the user's own accounts, "
    "or anything unclear that fits none of the groups."
)


def _slugs(names: list[str], reserved: set[str] = frozenset()) -> dict[str, str]:
    """Deterministic ASCII option keys -> original names, unique even after collapsing."""
    out: dict[str, str] = {}
    for name in names:
        base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "option"
        slug, n = base, 2
        while slug in out or slug in reserved:
            slug, n = f"{base}_{n}", n + 1
        out[slug] = name
    return out


GROUP_SLUGS = _slugs(list(CATEGORY_HIERARCHY), reserved={OTHER_OPTION})
GROUP_CRITERIA = {
    **{slug: f"{name}: {', '.join(CATEGORY_HIERARCHY[name])}" for slug, name in GROUP_SLUGS.items()},
    OTHER_OPTION: OTHER_DESCRIPTION,
}
CATEGORY_SLUGS = {group: _slugs(cats) for group, cats in CATEGORY_HIERARCHY.items()}


def _score(answer) -> float:
    if answer.confidence is not None:
        return answer.confidence
    return answer.probabilities.get(answer.choice, 0.0)


class JevAgent(CategorizationAgent):
    """Line-by-line classification with OpenRouter's Jev decision model: one
    group question, then one sub-category question limited to that group."""

    provider = "openrouter"
    label = "OpenRouter"
    env_var = "OPENROUTER_API_KEY"

    @property
    def model(self) -> str:
        return JEV_MODEL

    def __init__(self, api_key: str | None = None, threshold: float | None = None, transport=None):
        self._api_key = api_key
        self._threshold = threshold
        self._transport = transport

    @property
    def api_key(self) -> str:
        return settings.openrouter_api_key if self._api_key is None else self._api_key

    @property
    def threshold(self) -> float:
        return settings.jev_confidence_threshold if self._threshold is None else self._threshold

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _unresolved(self, txn: dict, reason: str) -> dict:
        # Seam: a future LLM fallback or composite agent would handle the line here.
        return dict(UNCATEGORIZED)

    async def classify(self, transactions: list[dict]) -> list[dict]:
        if not transactions:
            return []
        semaphore = asyncio.Semaphore(JEV_MAX_CONCURRENCY)
        auth_failed = asyncio.Event()
        outcomes: list[dict] = []

        async with httpx.AsyncClient(timeout=JEV_REQUEST_TIMEOUT_SECONDS, transport=self._transport) as client:

            async def one(index: int, txn: dict) -> dict:
                queued = time.perf_counter()
                outcome = {
                    "line": index, "state": _state(txn), "group": None, "category": None,
                    "group_score": None, "category_score": None, "cat_real": False,
                    "decision": None, "cost": None, "queue_ms": 0.0, "total_ms": 0.0,
                }
                outcomes.append(outcome)
                async with semaphore:
                    started = time.perf_counter()
                    outcome["queue_ms"] = (started - queued) * 1000
                    try:
                        if auth_failed.is_set():
                            outcome["decision"] = "auth"
                            return self._unresolved(txn, "auth")
                        try:
                            return await self._classify_line(client, txn, outcome)
                        except DecisionsAuthError:
                            auth_failed.set()
                            outcome["decision"] = "auth"
                            log_event(
                                logger, "jev_line", level=logging.ERROR, model=JEV_MODEL,
                                ok=False, error="DecisionsAuthError", fallback="skip_remaining",
                            )
                        except Exception as e:
                            outcome["decision"] = "error"
                            log_event(
                                logger, "jev_line", level=logging.WARNING, model=JEV_MODEL, line=index,
                                ok=False, fallback="uncategorized", error=type(e).__name__,
                                status_code=getattr(e, "status_code", None),
                            )
                        return self._unresolved(txn, "error")
                    finally:
                        outcome["total_ms"] = elapsed_ms(started)

            results = list(await asyncio.gather(*(one(i, t) for i, t in enumerate(transactions))))

        outcomes.sort(key=lambda o: o["line"])
        for o in outcomes:
            agent_trace.write(self.provider, {
                "model": JEV_MODEL, "stage": "line", "line": o["line"], "input": {"state": o["state"]},
                "group": o["group"], "category": o["category"], "group_score": o["group_score"],
                "category_score": o["category_score"], "decision": o["decision"],
                "threshold": self.threshold, "queue_ms": o["queue_ms"], "total_ms": o["total_ms"],
                "cost": o["cost"],
            })
        self.last_run_stats = _run_stats(outcomes)
        return results

    async def _decide(self, client, outcome: dict, question_id: str, instructions: str, criteria: dict):
        """Returns (answer, trace record awaiting its decision). Failed calls are traced here."""
        started = time.perf_counter()
        record = {
            "model": JEV_MODEL, "stage": question_id, "line": outcome["line"],
            "input": {"state": outcome["state"], "options": list(criteria)},
            "queue_ms": outcome["queue_ms"] if question_id == "group" else 0.0,
            "threshold": self.threshold,
        }
        try:
            answer = await decide_choice(
                client, api_key=self.api_key, state=outcome["state"], question_id=question_id,
                instructions=instructions, criteria=criteria,
            )
        except Exception as e:
            agent_trace.write(self.provider, {
                **record, "output": None, "ms": elapsed_ms(started), "attempts": getattr(e, "attempts", None),
                "status": type(e).__name__, "status_code": getattr(e, "status_code", None),
                "cost": None, "decision": "auth" if isinstance(e, DecisionsAuthError) else "error",
            })
            raise
        top = sorted(answer.probabilities.items(), key=lambda kv: kv[1], reverse=True)[:3]
        record.update(
            output={
                "choice": answer.choice, "confidence": answer.confidence,
                "top": [[key, prob] for key, prob in top],
            },
            ms=elapsed_ms(started), attempts=answer.attempts, status="ok", status_code=None, cost=answer.cost,
        )
        if answer.cost is not None:
            outcome["cost"] = (outcome["cost"] or 0.0) + answer.cost
        return answer, record

    async def _classify_line(self, client: httpx.AsyncClient, txn: dict, outcome: dict) -> dict:
        group_answer, record = await self._decide(client, outcome, "group", GROUP_INSTRUCTIONS, GROUP_CRITERIA)
        group_score = _score(group_answer)
        outcome["group_score"] = group_score
        if group_answer.choice == OTHER_OPTION:
            record["decision"] = outcome["decision"] = "other"
        else:
            outcome["group"] = GROUP_SLUGS[group_answer.choice]
            record["decision"] = outcome["decision"] = "group_low" if group_score < self.threshold else "accepted"
        agent_trace.write(self.provider, record)
        if outcome["decision"] != "accepted":
            return self._unresolved(txn, "group")
        group = outcome["group"]

        slugs = CATEGORY_SLUGS[group]
        if len(slugs) == 1:
            (category,) = slugs.values()
            cat_score = 1.0
            outcome["category"], outcome["category_score"] = category, cat_score
        else:
            cat_answer, record = await self._decide(
                client, outcome, "category", CATEGORY_INSTRUCTIONS.format(group=group), {s: n for s, n in slugs.items()},
            )
            cat_score = _score(cat_answer)
            outcome["category_score"], outcome["cat_real"] = cat_score, True
            category = slugs[cat_answer.choice]
            outcome["category"] = category
            record["decision"] = outcome["decision"] = "category_low" if cat_score < self.threshold else "accepted"
            agent_trace.write(self.provider, record)
            if cat_score < self.threshold:
                return self._unresolved(txn, "category")

        return {
            "general_category": group,
            "precise_category": category,
            "confidence": min(group_score, cat_score),
        }


def _state(txn: dict) -> dict:
    return {
        "description": txn["description"],
        "amount": str(txn["original_amount"]),
        "currency": txn["original_currency"],
        "bank": txn["bank"],
    }


def _run_stats(outcomes: list[dict]) -> dict:
    decisions = [o["decision"] for o in outcomes]
    stats: dict = {
        "accepted": decisions.count("accepted"),
        "group_other": decisions.count("other"),
        "group_low": decisions.count("group_low"),
        "category_low": decisions.count("category_low"),
        "errors": decisions.count("error"),
        "auth": decisions.count("auth"),
    }
    spreads = (
        ("group", [o["group_score"] for o in outcomes if o["group_score"] is not None]),
        ("cat", [o["category_score"] for o in outcomes if o["cat_real"]]),
    )
    for prefix, scores in spreads:
        if scores:
            stats[f"{prefix}_score_min"] = min(scores)
            stats[f"{prefix}_score_p50"] = statistics.median(scores)
            stats[f"{prefix}_score_max"] = max(scores)
    return stats

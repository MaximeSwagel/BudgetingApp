import asyncio
import logging
import re

import httpx

from app.config import settings
from app.observability import log_event
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

        async with httpx.AsyncClient(timeout=JEV_REQUEST_TIMEOUT_SECONDS, transport=self._transport) as client:

            async def one(index: int, txn: dict) -> dict:
                async with semaphore:
                    if auth_failed.is_set():
                        return self._unresolved(txn, "auth")
                    try:
                        return await self._classify_line(client, txn)
                    except DecisionsAuthError:
                        auth_failed.set()
                        log_event(
                            logger, "jev_line", level=logging.ERROR, model=JEV_MODEL,
                            ok=False, error="DecisionsAuthError", fallback="skip_remaining",
                        )
                    except Exception as e:
                        log_event(
                            logger, "jev_line", level=logging.WARNING, model=JEV_MODEL, line=index,
                            ok=False, fallback="uncategorized", error=type(e).__name__,
                            status_code=getattr(e, "status_code", None),
                        )
                    return self._unresolved(txn, "error")

            return list(await asyncio.gather(*(one(i, t) for i, t in enumerate(transactions))))

    async def _classify_line(self, client: httpx.AsyncClient, txn: dict) -> dict:
        state = {
            "description": txn["description"],
            "amount": str(txn["original_amount"]),
            "currency": txn["original_currency"],
            "bank": txn["bank"],
        }
        group_answer = await decide_choice(
            client, api_key=self.api_key, state=state, question_id="group",
            instructions=GROUP_INSTRUCTIONS, criteria=GROUP_CRITERIA,
        )
        group_score = _score(group_answer)
        if group_answer.choice == OTHER_OPTION or group_score < self.threshold:
            return self._unresolved(txn, "group")
        group = GROUP_SLUGS[group_answer.choice]

        slugs = CATEGORY_SLUGS[group]
        if len(slugs) == 1:
            (category,) = slugs.values()
            cat_score = 1.0
        else:
            cat_answer = await decide_choice(
                client, api_key=self.api_key, state=state, question_id="category",
                instructions=CATEGORY_INSTRUCTIONS.format(group=group), criteria={s: n for s, n in slugs.items()},
            )
            cat_score = _score(cat_answer)
            if cat_score < self.threshold:
                return self._unresolved(txn, "category")
            category = slugs[cat_answer.choice]

        return {
            "general_category": group,
            "precise_category": category,
            "confidence": min(group_score, cat_score),
        }

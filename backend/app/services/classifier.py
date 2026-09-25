import logging
import time

from app.config import settings
from app.observability import elapsed_ms, log_event
from app.services.agents.base import UNCATEGORIZED, CategorizationAgent
from app.services.agents.registry import build_agent

logger = logging.getLogger(__name__)


def get_active_agent() -> CategorizationAgent:
    # Resolved per call so a runtime change of ai_provider applies immediately.
    return build_agent(settings.ai_provider)


async def resolve_category_id(cat_data: dict, group_repo, category_repo) -> int | None:
    """Map a categorizer result to a category id, or None when it produced
    nothing usable (the transaction then stays honestly uncategorized).
    Shared by CSV upload and the bulk auto-categorize endpoint."""
    general = cat_data.get("general_category", "Uncategorized")
    precise = cat_data.get("precise_category", "Uncategorized")

    if general == "Uncategorized":
        return None
    group = await group_repo.get_by_name(general)
    if not group:
        return None
    cat = await category_repo.get_by_name_in_group(precise, group.id)
    if not cat:
        cat = await category_repo.first_in_group(group.id)
    return cat.id if cat else None


def _guard_contract(results, expected: int) -> list[dict]:
    """Persistence zips results with transactions, so a misbehaving agent
    must never be able to misalign or shorten them."""
    items = list(results) if isinstance(results, list) else []
    items = [r if isinstance(r, dict) else dict(UNCATEGORIZED) for r in items[:expected]]
    items.extend(dict(UNCATEGORIZED) for _ in range(expected - len(items)))
    return items


async def categorize_transactions(transactions: list[dict]) -> list[dict]:
    if not transactions:
        return []

    agent = get_active_agent()
    if not agent.is_configured():
        log_event(
            logger, "llm_categorize", level=logging.WARNING, provider=agent.provider, model=agent.model,
            rows=len(transactions), ok=False, skipped="no_api_key",
        )
        return [dict(UNCATEGORIZED) for _ in transactions]

    start = time.perf_counter()
    try:
        results = await agent.classify(transactions)
    except Exception as e:
        log_event(
            logger, "llm_categorize", level=logging.ERROR, provider=agent.provider, model=agent.model,
            rows=len(transactions), ok=False, error=type(e).__name__,
        )
        results = []
    results = _guard_contract(results, len(transactions))
    uncategorized = sum(1 for r in results if r.get("general_category") == "Uncategorized")
    log_event(
        logger, "llm_categorize", provider=agent.provider, model=agent.model, rows=len(transactions),
        uncategorized=uncategorized, ms=elapsed_ms(start),
    )
    return results

import logging
import math
import re
import time

from app import agent_trace
from app.config import settings
from app.observability import elapsed_ms, log_event
from app.services.agents.base import UNCATEGORIZED, CategorizationAgent
from app.services.agents.registry import build_agent
from app.services.taxonomy import load_category_hierarchy

logger = logging.getLogger(__name__)

_STAT_KEY = re.compile(r"[a-z][a-z0-9_]{0,31}")
_RESERVED_STAT_KEYS = {"event", "provider", "model", "rows", "uncategorized", "ms", "run", "ok", "error", "skipped"}


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


def _safe_stats(raw) -> dict:
    """Agent stats end up in a log line: keep only well-formed keys with numeric values."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not _STAT_KEY.fullmatch(key) or key in _RESERVED_STAT_KEYS:
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            out[key] = value
        elif isinstance(value, float) and math.isfinite(value):
            out[key] = f"{value:.2f}"
    return out


async def categorize_transactions(transactions: list[dict]) -> list[dict]:
    if not transactions:
        return []
    with agent_trace.trace_run() as run_id:
        return await _categorize(transactions, run_id)


async def _categorize(transactions: list[dict], run_id: str) -> list[dict]:
    agent = get_active_agent()
    rows = len(transactions)
    if not agent.is_configured():
        log_event(
            logger, "llm_categorize", level=logging.WARNING, provider=agent.provider, model=agent.model,
            rows=rows, ok=False, skipped="no_api_key", run=run_id,
        )
        agent_trace.write(agent.provider, {
            "model": agent.model, "stage": "run", "rows": rows, "uncategorized": rows,
            "stats": {}, "ms": 0.0, "status": "no_api_key",
        })
        return [dict(UNCATEGORIZED) for _ in transactions]

    start = time.perf_counter()
    status = "ok"
    stats: dict = {}
    try:
        categories = await load_category_hierarchy()
        results = await agent.classify(transactions, categories)
        stats = _safe_stats(getattr(agent, "last_run_stats", None))
    except Exception as e:
        status = type(e).__name__
        log_event(
            logger, "llm_categorize", level=logging.ERROR, provider=agent.provider, model=agent.model,
            rows=rows, ok=False, error=status, run=run_id,
        )
        results = []
    results = _guard_contract(results, rows)
    uncategorized = sum(1 for r in results if r.get("general_category") == "Uncategorized")
    ms = elapsed_ms(start)
    log_event(
        logger, "llm_categorize", provider=agent.provider, model=agent.model, rows=rows,
        uncategorized=uncategorized, **stats, ms=ms, run=run_id,
    )
    agent_trace.write(agent.provider, {
        "model": agent.model, "stage": "run", "rows": rows, "uncategorized": uncategorized,
        "stats": stats, "ms": ms, "status": status,
    })
    return results

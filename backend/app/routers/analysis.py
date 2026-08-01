from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.repositories import TransactionRepository

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

UNCATEGORIZED = "Uncategorized"


def _day_str(d) -> str:
    """`func.date(...)` returns a str under SQLite (test DB) and a `date`
    object under Postgres (runtime DB) -- normalize both to ISO text."""
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


@router.get("")
async def analysis(db: AsyncSession = Depends(get_db), days: int = Query(90, ge=1, le=365)):
    """Single read-only data-integrity payload for the Analysis page: sanity
    checks that CSV imports and AI categorization landed correctly. Mirrors
    the GET /api/dashboard "one fat endpoint" convention -- no writes here.

    `days` only bounds the `daily` series (window ending today); every other
    view spans all non-duplicate transactions. All monetary values are
    base-currency (converted_amount) sums except `by_currency`, which
    intentionally exposes pre-conversion original_amount grouped by
    original_currency.
    """
    repo = TransactionRepository(db)
    since = datetime.utcnow() - timedelta(days=days)

    # --- daily spend, both modes (aggregate total + by-category breakdown) ---
    daily_rows = await repo.daily_category_spend(since)
    daily_map: dict[str, dict[str, Decimal]] = {}
    for row in daily_rows:
        day = _day_str(row.day)
        category_name = row.category_name or UNCATEGORIZED
        bucket = daily_map.setdefault(day, {})
        bucket[category_name] = bucket.get(category_name, Decimal("0")) + abs(row.total or Decimal("0"))

    daily = [
        {
            "date": day,
            "total": str(sum(cats.values())),
            "by_category": {name: str(total) for name, total in cats.items()},
        }
        for day, cats in sorted(daily_map.items())
    ]

    # --- category distribution, largest spend first ---
    category_rows = await repo.category_distribution()
    categories = sorted(
        (
            {
                "group": row.group_name,
                "category": row.category_name,
                "total": str(abs(row.total or Decimal("0"))),
                "count": row.count,
            }
            for row in category_rows
        ),
        key=lambda c: Decimal(c["total"]),
        reverse=True,
    )

    uncategorized_count = await repo.count_uncategorized()

    # --- duplicate detector ---
    duplicate_groups = [
        {
            "date": g["day"].isoformat(),
            "amount": str(g["amount"]),
            "description": g["description"],
            "banks": g["banks"],
            "count": g["count"],
        }
        for g in await repo.duplicate_groups()
    ]

    # --- currency breakdown (pre-conversion) ---
    by_currency = [
        {
            "currency": row.original_currency,
            "original_total": str(row.original_total) if row.original_total is not None else "0",
            "converted_total": str(row.converted_total) if row.converted_total is not None else None,
            "count": row.count,
        }
        for row in await repo.currency_breakdown()
    ]

    # --- per-bank counts ---
    by_bank = [
        {"bank": row["bank"], "count": row["count"], "total": str(row["total"])}
        for row in await repo.bank_breakdown()
    ]

    return {
        "base_currency": settings.base_currency,
        "days": days,
        "daily": daily,
        "categories": categories,
        "uncategorized_count": uncategorized_count,
        "duplicate_groups": duplicate_groups,
        "by_currency": by_currency,
        "by_bank": by_bank,
    }

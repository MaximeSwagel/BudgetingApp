from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.repositories import TransactionRepository, UserSettingsRepository
from app.services.recurring import RECURRING_THRESHOLD_KEY, TxnRow, detect_recurring_large_expenses

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

UNCATEGORIZED = "Uncategorized"


def _day_str(d) -> str:
    """`func.date(...)` returns a str under SQLite (test DB) and a `date`
    object under Postgres (runtime DB) -- normalize both to ISO text."""
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def _serialize_recurring(g) -> dict:
    return {
        "merchant_key": g.merchant_key,
        "description": g.description,
        "category": g.category,
        "group": g.group,
        "occurrences": g.occurrences,
        "occurrence_count": len(g.occurrences),
        "latest_amount": str(g.latest_amount),
        "baseline_amount": str(g.baseline_amount),
        "pct_change": str(g.pct_change) if g.pct_change is not None else None,
        "status": g.status,
        "overdue": g.overdue,
        "last_seen": g.last_seen.date().isoformat() if g.last_seen else None,
    }


@router.get("")
async def analysis(
    db: AsyncSession = Depends(get_db),
    days: int = Query(90, ge=1, le=365),
    exclude_recurring: bool = Query(
        False, description="Exclude detected recurring large expenses from the aggregates below"
    ),
):
    """Single read-only data-integrity payload for the Analysis page: sanity
    checks that CSV imports and AI categorization landed correctly. Mirrors
    the GET /api/dashboard "one fat endpoint" convention -- no writes here.

    `days` only bounds the `daily` series (window ending today); every other
    view spans all non-duplicate transactions. All monetary values are
    base-currency (converted_amount) sums except `by_currency`, which
    intentionally exposes pre-conversion original_amount grouped by
    original_currency.

    `recurring` surfaces merchants that recur across >=3 months at/above the
    user's configured threshold (see app.services.recurring), each flagged
    "stable"/"increased"/"decreased" against their own baseline plus an
    `overdue` flag when one hasn't shown up recently -- the warning signal
    for "these big expenses changed". When `exclude_recurring` is set, every
    transaction belonging to a detected group is dropped from `daily`,
    `categories`, `by_currency`, and `by_bank` (but not `recurring` itself,
    `uncategorized_count`, or `duplicate_groups`, which are unaffected by
    this toggle).
    """
    repo = TransactionRepository(db)
    settings_repo = UserSettingsRepository(db)
    since = datetime.utcnow() - timedelta(days=days)

    # --- recurring large expenses ---
    threshold_row = await settings_repo.get_by_key(RECURRING_THRESHOLD_KEY)
    threshold = Decimal(threshold_row.value) if threshold_row else Decimal(str(settings.recurring_large_threshold))

    recurring_rows = await repo.list_expense_rows_for_recurring()
    recurring_groups = detect_recurring_large_expenses(
        [
            TxnRow(
                id=row.id,
                description=row.description,
                date=row.date,
                amount=abs(row.converted_amount),
                category_name=row.category_name,
                group_name=row.group_name,
            )
            for row in recurring_rows
        ],
        threshold,
    )
    recurring = [_serialize_recurring(g) for g in recurring_groups]

    exclude_ids: set[int] | None = None
    if exclude_recurring:
        exclude_ids = {tid for g in recurring_groups for tid in g.transaction_ids}

    # --- daily spend, both modes (aggregate total + by-category breakdown) ---
    daily_rows = await repo.daily_category_spend(since, exclude_ids=exclude_ids)
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
    category_rows = await repo.category_distribution(exclude_ids=exclude_ids)
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
        for row in await repo.currency_breakdown(exclude_ids=exclude_ids)
    ]

    # --- per-bank counts ---
    by_bank = [
        {"bank": row["bank"], "count": row["count"], "total": str(row["total"])}
        for row in await repo.bank_breakdown(exclude_ids=exclude_ids)
    ]

    return {
        "base_currency": settings.base_currency,
        "days": days,
        "daily": daily,
        "categories": categories,
        "uncategorized_count": uncategorized_count,
        "duplicate_groups": duplicate_groups,
        "recurring": recurring,
        "recurring_threshold": str(threshold),
        "exclude_recurring": exclude_recurring,
        "by_currency": by_currency,
        "by_bank": by_bank,
    }

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.repositories import TransactionRepository

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _last_months(now: datetime, count: int) -> list[tuple[int, int]]:
    """(year, month) pairs for the last `count` months, oldest first, ending now."""
    months = []
    year, month = now.year, now.month
    for _ in range(count):
        months.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(months))


@router.get("")
async def dashboard(db: AsyncSession = Depends(get_db), months: int = Query(6, ge=1, le=24)):
    repo = TransactionRepository(db)
    now = datetime.utcnow()
    month_keys = _last_months(now, months)

    since = datetime(month_keys[0][0], month_keys[0][1], 1)
    rows = await repo.monthly_totals_since(since)

    totals: dict[tuple[int, int], dict[str, Decimal]] = {
        key: {"expenses": Decimal("0"), "income": Decimal("0")} for key in month_keys
    }
    for row in rows:
        key = (int(row.year), int(row.month))
        if key not in totals:
            continue
        bucket = "expenses" if row.is_expense else "income"
        totals[key][bucket] += abs(row.total or Decimal("0"))

    group_rows = await repo.group_totals_for_month(now.year, now.month)
    by_group = sorted(
        ({"group": r.group_name, "total": str(abs(r.total or Decimal("0")))} for r in group_rows),
        key=lambda g: Decimal(g["total"]),
        reverse=True,
    )

    uncategorized_count = await repo.count_uncategorized()

    return {
        "base_currency": settings.base_currency,
        "months": [
            {
                "year": y,
                "month": m,
                "expenses": str(totals[(y, m)]["expenses"]),
                "income": str(totals[(y, m)]["income"]),
            }
            for y, m in month_keys
        ],
        "current_month": {
            "year": now.year,
            "month": now.month,
            "expenses": str(totals[(now.year, now.month)]["expenses"]),
            "income": str(totals[(now.year, now.month)]["income"]),
            "by_group": by_group,
        },
        "uncategorized_count": uncategorized_count,
    }

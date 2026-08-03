from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories import CategoryGroupRepository, CategoryGroupTargetRepository, TransactionRepository

router = APIRouter(prefix="/api/budget", tags=["budget"])

SUGGESTION_WINDOW_MONTHS = 3


def _recent_months(today: date, count: int = SUGGESTION_WINDOW_MONTHS) -> list[tuple[int, int]]:
    """The `count` full calendar months immediately before the month
    containing `today`, oldest first. Deliberately excludes the current,
    still-in-progress month -- including a partial month would skew a
    spending average low."""
    months: list[tuple[int, int]] = []
    year, month = today.year, today.month
    for _ in range(count):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
        months.append((year, month))
    months.reverse()
    return months


async def _suggested_targets(
    txn_repo: TransactionRepository, name_to_group_id: dict[str, int]
) -> dict[int, Decimal]:
    """Auto-proposed target per group: average recent monthly expense
    magnitude over the last SUGGESTION_WINDOW_MONTHS completed calendar
    months, rounded to a whole unit. Reuses `group_totals_for_month`
    (already used elsewhere) once per window month rather than adding a
    new repository query.

    The divisor is the count of window months that had ANY expense
    activity across ALL groups, not just this group's own active months --
    a group that was silent in an otherwise-active month should have that
    silence pull its average down, not be excluded from the denominator
    (which would inflate its suggestion toward months it happened to have
    spend in).
    """
    totals: dict[int, Decimal] = {}
    active_months = 0
    for year, month in _recent_months(date.today()):
        rows = await txn_repo.group_totals_for_month(year, month)
        if rows:
            active_months += 1
        for row in rows:
            group_id = name_to_group_id.get(row.group_name)
            if group_id is None:
                continue
            totals[group_id] = totals.get(group_id, Decimal("0")) + abs(row.total or Decimal("0"))

    if active_months == 0:
        return {}

    suggestions: dict[int, Decimal] = {}
    for group_id, total in totals.items():
        whole = (total / active_months).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if whole > 0:
            suggestions[group_id] = whole.quantize(Decimal("0.01"))
    return suggestions


def _current_month_start() -> date:
    """The real-world "now" month-start a target write is stored against
    (D-03). Used only by the write endpoints (POST/DELETE) below -- the
    summary read no longer consults it at all, since a group's target now
    applies uniformly to every month regardless of when it was set.
    Deliberately derived from `date.today()`, never from the `year` query
    parameter of the summary endpoint -- the year dropdown only changes
    what's being VIEWED, not what month a write is recorded against."""
    return date.today().replace(day=1)


@router.get("/summary")
async def budget_summary(
    db: AsyncSession = Depends(get_db),
    year: int = Query(2026),
):
    txn_repo = TransactionRepository(db)
    rows = await txn_repo.monthly_category_totals(year)

    group_repo = CategoryGroupRepository(db)
    all_groups = await group_repo.list_with_categories()

    target_repo = CategoryGroupTargetRepository(db)
    targets_by_group = await target_repo.current_targets_by_month()
    current_by_group = await target_repo.current_targets()
    suggested_by_group = await _suggested_targets(
        txn_repo, {g.name: g.id for g in all_groups}
    )

    spending: dict[str, dict[str, dict[int, Decimal]]] = {}
    for row in rows:
        month = int(row.month)
        group_name = row.group_name
        cat_name = row.category_name
        total = row.total or Decimal("0")

        spending.setdefault(group_name, {}).setdefault(cat_name, {})[month] = total

    budget_data = []
    for group in all_groups:
        group_data = {
            "group": group.name,
            "group_id": group.id,
            "categories": [],
            "monthly_totals": {},
            "annual_total": Decimal("0"),
        }

        for cat in sorted(group.categories, key=lambda c: c.display_order):
            cat_data = {
                "name": cat.name,
                "category_id": cat.id,
                "months": {},
                "annual_total": Decimal("0"),
            }

            for month in range(1, 13):
                amount = spending.get(group.name, {}).get(cat.name, {}).get(month, Decimal("0"))
                cat_data["months"][month] = str(amount)
                cat_data["annual_total"] += amount

                group_data["monthly_totals"][month] = str(
                    Decimal(group_data["monthly_totals"].get(month, "0")) + amount
                )

            cat_data["annual_total"] = str(cat_data["annual_total"])
            group_data["annual_total"] += Decimal(cat_data["annual_total"])
            group_data["categories"].append(cat_data)

        group_data["annual_total"] = str(group_data["annual_total"])
        # Targets are group-level only (D-01/D-06) and are emitted as
        # POSITIVE strings -- never negated to match the negative expense
        # convention. The magnitude comparison happens on the client (D-08).
        group_targets = targets_by_group.get(group.id, {})
        group_data["targets"] = {
            month: (str(v) if v is not None else None) for month, v in group_targets.items()
        }
        current_target = current_by_group.get(group.id)
        group_data["current_target"] = str(current_target) if current_target is not None else None
        # Only propose a suggestion when the group has no target yet (D-01
        # of this plan) -- once a target exists the user has already made
        # the call, and re-surfacing a computed number would read as a
        # second opinion nobody asked for.
        suggested_target = suggested_by_group.get(group.id) if current_target is None else None
        group_data["suggested_target"] = str(suggested_target) if suggested_target is not None else None
        budget_data.append(group_data)

    total_expense_monthly: dict[int, Decimal] = {}
    total_expense_annual = Decimal("0")
    for gd in budget_data:
        for month in range(1, 13):
            val = Decimal(gd["monthly_totals"].get(month, "0"))
            total_expense_monthly[month] = total_expense_monthly.get(month, Decimal("0")) + val
        total_expense_annual += Decimal(gd["annual_total"])

    return {
        "year": year,
        "groups": budget_data,
        "total_expense_monthly": {m: str(v) for m, v in total_expense_monthly.items()},
        "total_expense_annual": str(total_expense_annual),
    }


@router.post("/group-targets")
async def set_group_target(body: dict, db: AsyncSession = Depends(get_db)):
    """Upserts the target for the current real-world month (D-03) -- never
    the year being viewed on the summary page. The stored amount then
    applies to every month the summary shows, past and future, until
    changed or cleared."""
    group_repo = CategoryGroupRepository(db)
    group = await group_repo.get(body.get("group_id"))
    if not group:
        raise HTTPException(status_code=404, detail="Primary category not found")

    try:
        amount = Decimal(str(body["amount"]))
    except (InvalidOperation, TypeError, KeyError):
        raise HTTPException(status_code=400, detail="amount must be a number")

    if amount < 0:
        raise HTTPException(status_code=400, detail="amount must be zero or greater")

    effective_month = _current_month_start()
    target_repo = CategoryGroupTargetRepository(db)
    await target_repo.upsert_for_month(
        group_id=group.id, amount=amount, effective_month=effective_month
    )
    await db.commit()

    return {
        "ok": True,
        "group_id": group.id,
        "amount": str(amount),
        "effective_month": effective_month.isoformat(),
    }


@router.delete("/group-targets/{group_id}")
async def clear_group_target(group_id: int, db: AsyncSession = Depends(get_db)):
    """Clears a group's target by writing a NULL-amount row for the current
    real-world month (D-05) rather than deleting rows -- deleting would
    resurrect whatever target preceded it. Writing a null row for the
    current month makes it the group's latest row, so no month shows a
    target (past or future) until a new one is set."""
    group_repo = CategoryGroupRepository(db)
    group = await group_repo.get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Primary category not found")

    effective_month = _current_month_start()
    target_repo = CategoryGroupTargetRepository(db)
    await target_repo.upsert_for_month(
        group_id=group.id, amount=None, effective_month=effective_month
    )
    await db.commit()

    return {"ok": True, "group_id": group.id, "effective_month": effective_month.isoformat()}

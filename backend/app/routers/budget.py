from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import BudgetTarget, Category, CategoryGroup, Transaction

router = APIRouter(prefix="/api/budget", tags=["budget"])


@router.get("/summary")
async def budget_summary(
    db: AsyncSession = Depends(get_db),
    year: int = Query(2026),
):
    result = await db.execute(
        select(
            extract("month", Transaction.date).label("month"),
            CategoryGroup.name.label("group_name"),
            Category.name.label("category_name"),
            func.sum(Transaction.converted_amount).label("total"),
        )
        .join(Transaction.category)
        .join(Category.group)
        .where(
            extract("year", Transaction.date) == year,
            Transaction.is_expense == True,  # noqa: E712
            Transaction.is_duplicate == False,  # noqa: E712
        )
        .group_by("month", "group_name", "category_name")
        .order_by("group_name", "category_name", "month")
    )
    rows = result.all()

    groups_result = await db.execute(
        select(CategoryGroup).options(joinedload(CategoryGroup.categories)).order_by(CategoryGroup.display_order)
    )
    all_groups = groups_result.scalars().unique().all()

    targets_result = await db.execute(
        select(BudgetTarget).where(BudgetTarget.year == year)
    )
    targets = targets_result.scalars().all()
    target_map = {(t.category_id, t.month): t.amount for t in targets}

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
                "targets": {},
            }

            for month in range(1, 13):
                amount = spending.get(group.name, {}).get(cat.name, {}).get(month, Decimal("0"))
                cat_data["months"][month] = str(amount)
                cat_data["annual_total"] += amount

                target = target_map.get((cat.id, month))
                if target is not None:
                    cat_data["targets"][month] = str(target)

                group_data["monthly_totals"][month] = str(
                    Decimal(group_data["monthly_totals"].get(month, "0")) + amount
                )

            cat_data["annual_total"] = str(cat_data["annual_total"])
            group_data["annual_total"] += Decimal(cat_data["annual_total"])
            group_data["categories"].append(cat_data)

        group_data["annual_total"] = str(group_data["annual_total"])
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


@router.post("/targets")
async def set_budget_target(body: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BudgetTarget).where(
            BudgetTarget.category_id == body["category_id"],
            BudgetTarget.year == body["year"],
            BudgetTarget.month == body["month"],
        )
    )
    target = result.scalar_one_or_none()

    if target:
        target.amount = Decimal(str(body["amount"]))
    else:
        target = BudgetTarget(
            category_id=body["category_id"],
            year=body["year"],
            month=body["month"],
            amount=Decimal(str(body["amount"])),
        )
        db.add(target)

    await db.commit()
    return {"ok": True}

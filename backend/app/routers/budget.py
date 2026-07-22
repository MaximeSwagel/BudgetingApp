from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import BudgetTarget
from app.repositories import BudgetTargetRepository, CategoryGroupRepository, TransactionRepository

router = APIRouter(prefix="/api/budget", tags=["budget"])


@router.get("/summary")
async def budget_summary(
    db: AsyncSession = Depends(get_db),
    year: int = Query(2026),
):
    txn_repo = TransactionRepository(db)
    rows = await txn_repo.monthly_category_totals(year)

    group_repo = CategoryGroupRepository(db)
    all_groups = await group_repo.list_with_categories()

    target_repo = BudgetTargetRepository(db)
    targets = await target_repo.list_by_year(year)
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
    repo = BudgetTargetRepository(db)
    target = await repo.get_by_key(
        category_id=body["category_id"], year=body["year"], month=body["month"]
    )

    if target:
        target.amount = Decimal(str(body["amount"]))
    else:
        repo.add(
            BudgetTarget(
                category_id=body["category_id"],
                year=body["year"],
                month=body["month"],
                amount=Decimal(str(body["amount"])),
            )
        )

    await repo.commit()
    return {"ok": True}

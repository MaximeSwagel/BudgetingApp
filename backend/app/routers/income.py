from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.repositories import TransactionRepository
from app.services.income import IncomeRow, build_income_report

router = APIRouter(prefix="/api/income", tags=["income"])


@router.get("")
async def income(db: AsyncSession = Depends(get_db)):
    """Single read-only fat endpoint for the Income page (mirrors the
    GET /api/analysis convention). Never writes. Recurring streams are
    derived at read time on every call -- no persistence, no schema change
    (J-09 in the plan; see app.services.income for the detection algorithm).

    Amount resolution (J-08): `abs(converted_amount)` when not None, else
    `abs(original_amount)` -- the `is not None` check is mandatory, not a
    style preference, since a legitimate zero converted_amount must not
    silently fall back to the original. `unconverted_count` tells the UI how
    many rows used the fallback so it can caveat the totals honestly.
    """
    repo = TransactionRepository(db)
    rows = await repo.list_income()

    unconverted_count = 0
    income_rows: list[IncomeRow] = []
    for r in rows:
        if r.converted_amount is not None:
            amount = abs(r.converted_amount)
        else:
            amount = abs(r.original_amount)
            unconverted_count += 1
        income_rows.append(
            IncomeRow(
                id=r.id,
                date=r.date.date(),
                description=r.description,
                bank=r.bank,
                amount=amount,
                original_amount=r.original_amount,
                original_currency=r.original_currency,
            )
        )

    today = datetime.utcnow().date()
    report = build_income_report(
        income_rows,
        today=today,
        base_currency=settings.base_currency,
        unconverted_count=unconverted_count,
    )
    return {"generated_on": today.isoformat(), **report}

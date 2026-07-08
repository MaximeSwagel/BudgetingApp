from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories import TransactionRepository

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("")
async def list_transactions(
    db: AsyncSession = Depends(get_db),
    bank: str | None = Query(None),
    currency: str | None = Query(None),
    category_group: str | None = Query(None),
    category: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    repo = TransactionRepository(db)
    transactions, total = await repo.list_filtered(
        bank=bank,
        currency=currency,
        category_group=category_group,
        category=category,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "transactions": [
            {
                "id": t.id,
                "date": t.date.isoformat(),
                "description": t.description,
                "original_amount": str(t.original_amount),
                "original_currency": t.original_currency,
                "converted_amount": str(t.converted_amount) if t.converted_amount else None,
                "base_currency": t.base_currency,
                "exchange_rate": str(t.exchange_rate) if t.exchange_rate else None,
                "bank": t.bank,
                "category_group": t.category.group.name if t.category and t.category.group else None,
                "category": t.category.name if t.category else None,
                "category_id": t.category_id,
                "is_expense": t.is_expense,
            }
            for t in transactions
        ],
    }


@router.patch("/{transaction_id}/category")
async def update_transaction_category(
    transaction_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    repo = TransactionRepository(db)
    txn = await repo.get(transaction_id)
    if not txn:
        return {"error": "Transaction not found"}

    category_id = body.get("category_id")
    if category_id:
        txn.category_id = category_id
        await repo.commit()

    return {"ok": True}

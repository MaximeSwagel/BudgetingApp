from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import Transaction, Category, CategoryGroup

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
    query = (
        select(Transaction)
        .options(joinedload(Transaction.category).joinedload(Category.group))
        .where(Transaction.is_duplicate == False)  # noqa: E712
    )

    if bank:
        query = query.where(Transaction.bank == bank)
    if currency:
        query = query.where(Transaction.original_currency == currency)
    if date_from:
        query = query.where(Transaction.date >= date_from)
    if date_to:
        query = query.where(Transaction.date <= date_to)
    if category_group:
        query = query.join(Transaction.category).join(Category.group).where(CategoryGroup.name == category_group)
    if category:
        query = query.join(Transaction.category, isouter=True).where(Category.name == category)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(Transaction.date.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    transactions = result.scalars().unique().all()

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
    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    txn = result.scalar_one_or_none()
    if not txn:
        return {"error": "Transaction not found"}

    category_id = body.get("category_id")
    if category_id:
        txn.category_id = category_id
        await db.commit()

    return {"ok": True}

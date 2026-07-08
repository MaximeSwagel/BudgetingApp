from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.repositories import CategoryGroupRepository, CategoryRepository, TransactionRepository
from app.services.categorizer import categorize_transactions, resolve_category_id

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

# Bound one auto-categorize run so the HTTP request stays well under proxy
# timeouts (~10 OpenAI calls); the response reports what's left to do.
CATEGORIZE_BATCH_LIMIT = 300


@router.post("/categorize")
async def auto_categorize(db: AsyncSession = Depends(get_db)):
    """Run the AI categorizer over transactions that still have no category
    (e.g. imported while the OpenAI key/quota was missing)."""
    if not settings.openai_api_key:
        return {"error": "No OpenAI API key configured — add one, then retry."}

    repo = TransactionRepository(db)
    txns = await repo.list_uncategorized(limit=CATEGORIZE_BATCH_LIMIT)
    if not txns:
        return {"ok": True, "processed": 0, "categorized": 0, "remaining": 0}

    payload = [
        {
            "description": t.description,
            "original_amount": t.original_amount,
            "original_currency": t.original_currency,
            "bank": t.bank,
        }
        for t in txns
    ]
    results = await categorize_transactions(payload)

    group_repo = CategoryGroupRepository(db)
    category_repo = CategoryRepository(db)
    categorized = 0
    for txn, cat_data in zip(txns, results):
        category_id = await resolve_category_id(cat_data, group_repo, category_repo)
        if category_id is not None:
            txn.category_id = category_id
            categorized += 1

    await repo.commit()
    remaining = await repo.count_uncategorized()
    return {
        "ok": True,
        "processed": len(txns),
        "categorized": categorized,
        "remaining": remaining,
    }


@router.get("")
async def list_transactions(
    db: AsyncSession = Depends(get_db),
    bank: str | None = Query(None),
    currency: str | None = Query(None),
    category_group: str | None = Query(None),
    category: str | None = Query(None),
    uncategorized: bool = Query(False),
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
        uncategorized=uncategorized,
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

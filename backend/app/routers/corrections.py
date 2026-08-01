from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import CategoryCorrection
from app.repositories import CategoryCorrectionRepository, CategoryRepository, TransactionRepository
from app.services.corrections import MIN_KEY_LEN, match_key, normalize_merchant

router = APIRouter(prefix="/api/corrections", tags=["corrections"])


def _serialize(correction: CategoryCorrection) -> dict:
    return {
        "id": correction.id,
        "merchant_key": correction.merchant_key,
        "description_sample": correction.description_sample,
        "category_id": correction.category_id,
        "category": correction.category.name if correction.category else None,
        "category_group": correction.category.group.name if correction.category and correction.category.group else None,
        "created_at": correction.created_at.isoformat(),
    }


@router.get("")
async def list_corrections(db: AsyncSession = Depends(get_db)):
    repo = CategoryCorrectionRepository(db)
    corrections = await repo.list_all()
    return {"corrections": [_serialize(c) for c in corrections]}


@router.post("")
async def create_correction(body: dict, db: AsyncSession = Depends(get_db)):
    """Flag a transaction as miscategorized and, optionally, teach a
    merchant-level correction. Reads ONLY `transaction_id` and `category_id`
    off the body -- other keys are ignored, so a caller cannot set arbitrary
    columns (see threat T-260801-h7a-01)."""
    transaction_id = body.get("transaction_id")
    category_id = body.get("category_id")

    txn_repo = TransactionRepository(db)
    txn = await txn_repo.get(transaction_id)
    if not txn:
        return {"error": "Transaction not found"}

    merchant_key = normalize_merchant(txn.description)
    if not merchant_key or len(merchant_key) < MIN_KEY_LEN:
        return {
            "error": (
                "Description does not contain enough identifying text to learn a "
                "merchant rule (it would match almost everything)."
            )
        }

    if category_id is not None:
        category_repo = CategoryRepository(db)
        category = await category_repo.get(category_id)
        if not category:
            return {"error": "Category not found"}

    correction_repo = CategoryCorrectionRepository(db)
    existing = await correction_repo.get_by_merchant_key(merchant_key)

    if existing:
        existing.category_id = category_id
        existing.description_sample = txn.description
        existing.source_transaction_id = txn.id
        # original_category_id is preserved from first flag -- never overwritten.
        correction = existing
    else:
        correction = correction_repo.add(
            CategoryCorrection(
                merchant_key=merchant_key,
                description_sample=txn.description,
                category_id=category_id,
                original_category_id=txn.category_id,
                source_transaction_id=txn.id,
            )
        )

    updated_transactions = 0
    if category_id is not None:
        txn.category_id = category_id
        updated_transactions += 1

        first_token = merchant_key.split(" ")[0] if merchant_key else ""
        if first_token:
            candidates = await txn_repo.list_matching_candidates(first_token)
            for candidate in candidates:
                if candidate.id == txn.id:
                    continue
                if match_key(candidate.description, {merchant_key}) != merchant_key:
                    continue
                if candidate.category_id != category_id:
                    candidate.category_id = category_id
                    updated_transactions += 1

    await correction_repo.commit()
    # Reload via get_by_merchant_key (eager joinedload) rather than a plain
    # refresh(): refresh() only re-reads columns, leaving `category` a lazy
    # relationship that raises MissingGreenlet on the next async access.
    correction = await correction_repo.get_by_merchant_key(merchant_key)

    return {
        "ok": True,
        "correction": _serialize(correction),
        "updated_transactions": updated_transactions,
    }


@router.delete("/{correction_id}")
async def delete_correction(correction_id: int, db: AsyncSession = Depends(get_db)):
    """Remove a correction. Deliberately does NOT revert any transaction's
    category -- silently un-categorizing historical rows on delete would be
    surprising and destructive."""
    repo = CategoryCorrectionRepository(db)
    correction = await repo.get(correction_id)
    if not correction:
        return {"error": "Correction not found"}

    await repo.remove(correction)
    await repo.commit()
    return {"ok": True}

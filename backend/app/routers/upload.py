from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import ImportBatch, Transaction
from app.parsers import detect_bank_format, parse_credit_agricole, parse_revolut_en, parse_revolut_fr
from app.repositories import CategoryGroupRepository, CategoryRepository, ImportBatchRepository, TransactionRepository
from app.services.categorizer import categorize_transactions, resolve_category_id
from app.services.currency import convert_amount

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.delete("/batches/{batch_id}")
async def undo_import(batch_id: int, db: AsyncSession = Depends(get_db)):
    """Undo a CSV import: remove the batch and every transaction it created."""
    repo = ImportBatchRepository(db)
    batch = await repo.get(batch_id)
    if not batch:
        return {"error": "Import batch not found"}

    deleted = await repo.delete_with_transactions(batch_id)
    return {"ok": True, "deleted": deleted}


@router.post("")
async def upload_csv(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    content = await file.read()

    format_type = detect_bank_format(content)

    parsers = {
        "revolut_fr": parse_revolut_fr,
        "revolut_en": parse_revolut_en,
        "ca": parse_credit_agricole,
    }

    if format_type == "revolut_merged":
        return {"error": "Merged Revolut CSVs are not supported. Please upload per-currency account statements."}

    parser = parsers.get(format_type)
    if not parser:
        return {"error": f"Unsupported format: {format_type}"}

    parsed_transactions = parser(content)

    if not parsed_transactions:
        return {"error": "No valid transactions found in the CSV"}

    batch_repo = ImportBatchRepository(db)
    group_repo = CategoryGroupRepository(db)
    category_repo = CategoryRepository(db)
    txn_repo = TransactionRepository(db)

    bank = parsed_transactions[0]["bank"] if parsed_transactions else format_type
    batch = batch_repo.add(
        ImportBatch(
            filename=file.filename or "unknown.csv",
            bank=bank,
            imported_at=datetime.utcnow(),
            transaction_count=0,
        )
    )
    await batch_repo.flush()

    categories = await categorize_transactions(parsed_transactions)

    base_currency = settings.base_currency
    imported_count = 0
    duplicates = 0

    for txn_data, cat_data in zip(parsed_transactions, categories):
        # A failed/skipped categorization resolves to None and stays NULL
        # ("Uncategorized" in the UI) rather than being silently dumped into
        # a wrong category.
        category_id = await resolve_category_id(cat_data, group_repo, category_repo)

        orig_amount = txn_data["original_amount"]
        orig_currency = txn_data["original_currency"]
        date_str = txn_data["date"].strftime("%Y-%m-%d")

        if orig_currency != base_currency:
            converted, rate = await convert_amount(abs(orig_amount), orig_currency, base_currency, date_str)
            if orig_amount < 0:
                converted = -converted
        else:
            converted = orig_amount
            rate = Decimal("1")

        is_dup = (
            await txn_repo.find_duplicate(
                date=txn_data["date"],
                amount=orig_amount,
                currency=orig_currency,
                bank=txn_data["bank"],
                description=txn_data["description"],
            )
            is not None
        )

        if is_dup:
            duplicates += 1
            continue

        txn_repo.add(
            Transaction(
                date=txn_data["date"],
                description=txn_data["description"],
                original_amount=orig_amount,
                original_currency=orig_currency,
                converted_amount=converted,
                exchange_rate=rate,
                base_currency=base_currency,
                bank=txn_data["bank"],
                category_id=category_id,
                import_batch_id=batch.id,
                is_duplicate=False,
                is_expense=txn_data.get("is_expense", orig_amount < 0),
            )
        )
        imported_count += 1

    batch.transaction_count = imported_count
    await batch_repo.commit()

    return {
        "format_detected": format_type,
        "bank": bank,
        "total_parsed": len(parsed_transactions),
        "imported": imported_count,
        "duplicates_skipped": duplicates,
        "batch_id": batch.id,
    }

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Category, CategoryGroup, ImportBatch, Transaction
from app.parsers import detect_bank_format, parse_credit_agricole, parse_revolut_en, parse_revolut_fr
from app.services.categorizer import categorize_transactions
from app.services.currency import convert_amount

router = APIRouter(prefix="/api/upload", tags=["upload"])


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

    bank = parsed_transactions[0]["bank"] if parsed_transactions else format_type
    batch = ImportBatch(
        filename=file.filename or "unknown.csv",
        bank=bank,
        imported_at=datetime.utcnow(),
        transaction_count=0,
    )
    db.add(batch)
    await db.flush()

    categories = await categorize_transactions(parsed_transactions)

    base_currency = "ILS"
    imported_count = 0
    duplicates = 0

    for txn_data, cat_data in zip(parsed_transactions, categories):
        general_cat = cat_data.get("general_category", "Uncategorized")
        precise_cat = cat_data.get("precise_category", "Uncategorized")

        group_result = await db.execute(select(CategoryGroup).where(CategoryGroup.name == general_cat))
        group = group_result.scalar_one_or_none()
        if not group:
            group_result = await db.execute(select(CategoryGroup).where(CategoryGroup.name == "Discretionary"))
            group = group_result.scalar_one_or_none()

        category_id = None
        if group:
            cat_result = await db.execute(
                select(Category).where(Category.name == precise_cat, Category.group_id == group.id)
            )
            cat = cat_result.scalar_one_or_none()
            if not cat:
                cat_result = await db.execute(
                    select(Category).where(Category.group_id == group.id)
                )
                cat = cat_result.scalars().first()
            if cat:
                category_id = cat.id

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

        existing = await db.execute(
            select(Transaction).where(
                Transaction.date == txn_data["date"],
                Transaction.original_amount == orig_amount,
                Transaction.original_currency == orig_currency,
                Transaction.bank == txn_data["bank"],
                Transaction.description == txn_data["description"],
            )
        )
        is_dup = existing.scalar_one_or_none() is not None

        if is_dup:
            duplicates += 1
            continue

        txn = Transaction(
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
        db.add(txn)
        imported_count += 1

    batch.transaction_count = imported_count
    await db.commit()

    return {
        "format_detected": format_type,
        "bank": bank,
        "total_parsed": len(parsed_transactions),
        "imported": imported_count,
        "duplicates_skipped": duplicates,
        "batch_id": batch.id,
    }

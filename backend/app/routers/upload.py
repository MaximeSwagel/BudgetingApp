import logging
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import ImportBatch, Transaction, UploadLog
from app.parsers import detect_bank_format, parse_credit_agricole, parse_leumi, parse_revolut_en, parse_revolut_fr
from app.repositories import (
    CategoryCorrectionRepository,
    CategoryGroupRepository,
    CategoryRepository,
    ImportBatchRepository,
    TransactionRepository,
    UploadLogRepository,
)
from app.services.categorizer import categorize_transactions, resolve_category_id
from app.services.corrections import categorize_with_corrections, learned_categories
from app.services.currency import convert_amount
from app.services.transfer_scan import resolve_transfer_fee_category_id, scan_and_persist

router = APIRouter(prefix="/api/upload", tags=["upload"])
logger = logging.getLogger(__name__)


@router.delete("/batches/{batch_id}")
async def undo_import(batch_id: int, db: AsyncSession = Depends(get_db)):
    """Undo a CSV import: remove the batch and every transaction it created."""
    repo = ImportBatchRepository(db)
    batch = await repo.get(batch_id)
    if not batch:
        return {"error": "Import batch not found"}

    deleted = await repo.delete_with_transactions(batch_id)
    return {"ok": True, "deleted": deleted}


@router.get("/logs")
async def list_upload_logs(db: AsyncSession = Depends(get_db)):
    """Append-only audit trail of every upload attempt (success and failure),
    newest first. Independent of ImportBatch, so it survives undo/reset."""
    repo = UploadLogRepository(db)
    logs = await repo.list_recent()
    return {
        "logs": [
            {
                "id": log.id,
                "filename": log.filename,
                "bank": log.bank,
                "format_detected": log.format_detected,
                "uploaded_at": log.uploaded_at.isoformat(),
                "rows_parsed": log.rows_parsed,
                "rows_imported": log.rows_imported,
                "rows_skipped": log.rows_skipped,
                "rows_failed": log.rows_failed,
                "status": log.status,
                "error": log.error,
            }
            for log in logs
        ]
    }


async def _record_failed_upload(
    log_repo: UploadLogRepository,
    *,
    filename: str,
    error: str,
    bank: str | None = None,
    format_detected: str | None = None,
) -> None:
    log_repo.add(
        UploadLog(
            filename=filename,
            bank=bank,
            format_detected=format_detected,
            uploaded_at=datetime.utcnow(),
            rows_parsed=0,
            rows_imported=0,
            rows_skipped=0,
            rows_failed=0,
            status="failed",
            error=error,
        )
    )
    await log_repo.commit()


@router.post("")
async def upload_csv(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    content = await file.read()
    filename = file.filename or "unknown.csv"
    log_repo = UploadLogRepository(db)

    try:
        format_type = detect_bank_format(content)
    except ValueError as e:
        await _record_failed_upload(log_repo, filename=filename, error=str(e))
        return {"error": str(e)}

    parsers = {
        "revolut_fr": parse_revolut_fr,
        "revolut_en": parse_revolut_en,
        "ca": parse_credit_agricole,
        "leumi": parse_leumi,
    }

    if format_type == "revolut_merged":
        error = "Merged Revolut CSVs are not supported. Please upload per-currency account statements."
        await _record_failed_upload(log_repo, filename=filename, error=error, format_detected=format_type)
        return {"error": error}

    parser = parsers.get(format_type)
    if not parser:
        error = f"Unsupported format: {format_type}"
        await _record_failed_upload(log_repo, filename=filename, error=error, format_detected=format_type)
        return {"error": error}

    parsed_transactions = parser(content)

    if not parsed_transactions:
        error = "No valid transactions found in the CSV"
        await _record_failed_upload(log_repo, filename=filename, error=error, format_detected=format_type)
        return {"error": error}

    batch_repo = ImportBatchRepository(db)
    group_repo = CategoryGroupRepository(db)
    category_repo = CategoryRepository(db)
    txn_repo = TransactionRepository(db)

    bank = parsed_transactions[0]["bank"] if parsed_transactions else format_type
    batch = batch_repo.add(
        ImportBatch(
            filename=filename,
            bank=bank,
            imported_at=datetime.utcnow(),
            transaction_count=0,
        )
    )
    await batch_repo.flush()

    learned = learned_categories(await CategoryCorrectionRepository(db).key_map())
    categories = await categorize_with_corrections(parsed_transactions, learned, categorize_transactions)

    base_currency = settings.base_currency
    imported_count = 0
    duplicates = 0
    fees_recorded = 0

    # Resolved once per upload (not once per row) -- a missing category is a
    # soft failure, so a fee row lands uncategorized rather than the whole
    # upload failing (D-08/D-09).
    fee_category_id = await resolve_transfer_fee_category_id(group_repo, category_repo)

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

        # Synthesize a separate fee transaction when the parser extracted a
        # non-zero fee (currently only the Revolut parsers emit this field).
        # Read explicitly with `!= Decimal("0")`, never truthiness, so a
        # bug like D-14's zero-amount falsiness issue can't be copied here.
        fee = txn_data.get("fee")
        if fee is not None and fee != Decimal("0"):
            fee_amount = -abs(fee)
            # Em-dash suffix (matching the description style already used
            # elsewhere in this codebase) is what keeps this synthesized row
            # from colliding with uq_transaction_dedup on re-upload.
            fee_description = f"{txn_data['description']} — Transfer fee"

            if orig_currency != base_currency:
                fee_converted, fee_rate = await convert_amount(
                    abs(fee_amount), orig_currency, base_currency, date_str
                )
                fee_converted = -fee_converted
            else:
                fee_converted = fee_amount
                fee_rate = Decimal("1")

            fee_is_dup = (
                await txn_repo.find_duplicate(
                    date=txn_data["date"],
                    amount=fee_amount,
                    currency=orig_currency,
                    bank=txn_data["bank"],
                    description=fee_description,
                )
                is not None
            )

            if not fee_is_dup:
                txn_repo.add(
                    Transaction(
                        date=txn_data["date"],
                        description=fee_description,
                        original_amount=fee_amount,
                        original_currency=orig_currency,
                        converted_amount=fee_converted,
                        exchange_rate=fee_rate,
                        base_currency=base_currency,
                        bank=txn_data["bank"],
                        category_id=fee_category_id,
                        import_batch_id=batch.id,
                        is_duplicate=False,
                        is_expense=True,
                    )
                )
                fees_recorded += 1

    # Fee rows count toward the batch total so undo-import removes them too,
    # while the "imported" response key below stays principal-rows-only --
    # existing tests assert on that key's meaning.
    batch.transaction_count = imported_count + fees_recorded

    # rows_failed stays 0: the parsers silently drop malformed rows today and
    # don't surface a per-row failure count (see SUMMARY for this limitation).
    log_repo.add(
        UploadLog(
            filename=filename,
            bank=bank,
            format_detected=format_type,
            uploaded_at=datetime.utcnow(),
            rows_parsed=len(parsed_transactions),
            rows_imported=imported_count,
            rows_skipped=duplicates,
            rows_failed=0,
            status="success",
        )
    )

    # Same session/transaction as the batch + imported transactions above.
    await batch_repo.commit()

    # Run internal-transfer detection at the end of every successful upload
    # (D-07) -- wrapped so a detection failure logs and returns zero rather
    # than failing an otherwise successful import.
    try:
        scan_summary = await scan_and_persist(db)
        transfers_detected = scan_summary["created"]
    except Exception as e:
        logger.error(f"Transfer detection after upload failed: {e}")
        transfers_detected = 0

    return {
        "format_detected": format_type,
        "bank": bank,
        "total_parsed": len(parsed_transactions),
        "imported": imported_count,
        "duplicates_skipped": duplicates,
        "batch_id": batch.id,
        "fees_recorded": fees_recorded,
        "transfers_detected": transfers_detected,
    }

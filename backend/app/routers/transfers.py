from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import InternalTransferMatch
from app.repositories import TransactionRepository, TransferMatchRepository
from app.services.transfer_scan import scan_and_persist

router = APIRouter(prefix="/api/transfers", tags=["transfers"])


def _serialize_leg(txn) -> dict:
    return {
        "id": txn.id,
        "date": txn.date.isoformat(),
        "description": txn.description,
        "original_amount": str(txn.original_amount),
        "original_currency": txn.original_currency,
        "converted_amount": str(txn.converted_amount) if txn.converted_amount is not None else None,
        "bank": txn.bank,
        # bank:currency -- the only account identity available in this
        # codebase (D-04, see app.services.transfers.account_key).
        "account": f"{txn.bank}:{txn.original_currency}",
        "category": txn.category.name if txn.category else None,
    }


def _serialize_match(match: InternalTransferMatch, txn_by_id: dict) -> dict | None:
    """Reserializes a match from its two legs so `fee_amount` can never
    drift from the underlying rows. Returns None (skip, don't crash) when
    a leg no longer exists -- a data-integrity edge case."""
    outgoing = txn_by_id.get(match.outgoing_transaction_id)
    incoming = txn_by_id.get(match.incoming_transaction_id)
    if outgoing is None or incoming is None:
        return None

    day_gap = (incoming.date.date() - outgoing.date.date()).days

    fee_amount = None
    if outgoing.converted_amount is not None and incoming.converted_amount is not None:
        diff = abs(outgoing.converted_amount) - abs(incoming.converted_amount)
        if diff >= 0:
            fee_amount = diff

    return {
        "id": match.id,
        "confidence": match.confidence,
        "status": match.status,
        "detected_at": match.detected_at.isoformat(),
        "day_gap": day_gap,
        "fee_amount": str(fee_amount) if fee_amount is not None else None,
        "outgoing": _serialize_leg(outgoing),
        "incoming": _serialize_leg(incoming),
    }


async def _serialize_one(db: AsyncSession, match: InternalTransferMatch) -> dict | None:
    txn_repo = TransactionRepository(db)
    txns = await txn_repo.list_by_ids({match.outgoing_transaction_id, match.incoming_transaction_id})
    return _serialize_match(match, {t.id: t for t in txns})


@router.get("")
async def list_transfers(db: AsyncSession = Depends(get_db)):
    match_repo = TransferMatchRepository(db)
    txn_repo = TransactionRepository(db)

    matches = await match_repo.list_all()
    leg_ids = {m.outgoing_transaction_id for m in matches} | {m.incoming_transaction_id for m in matches}
    txn_by_id = {t.id: t for t in await txn_repo.list_by_ids(leg_ids)}

    serialized = [s for m in matches if (s := _serialize_match(m, txn_by_id)) is not None]

    confirmed = [s for s in serialized if s["status"] == "confirmed"]
    suggested_count = sum(1 for s in serialized if s["status"] == "suggested")
    rejected_count = sum(1 for s in serialized if s["status"] == "rejected")

    total_transferred = sum(
        (
            abs(Decimal(s["outgoing"]["converted_amount"]))
            for s in confirmed
            if s["outgoing"]["converted_amount"] is not None
        ),
        Decimal("0"),
    )
    total_fees = sum(
        (Decimal(s["fee_amount"]) for s in confirmed if s["fee_amount"] is not None),
        Decimal("0"),
    )

    return {
        "base_currency": settings.base_currency,
        "matches": serialized,
        "summary": {
            "confirmed_count": len(confirmed),
            "suggested_count": suggested_count,
            "rejected_count": rejected_count,
            "total_transferred": str(total_transferred),
            "total_fees": str(total_fees),
        },
    }


@router.post("/detect")
async def detect_transfers(db: AsyncSession = Depends(get_db)):
    """On-demand rescan -- the same `scan_and_persist` entry point the
    upload path calls automatically (D-07), so historical transactions
    already in the DB can be scanned without re-importing."""
    summary = await scan_and_persist(db)
    return {"ok": True, **summary}


@router.post("/{match_id}/confirm")
async def confirm_transfer(match_id: int, db: AsyncSession = Depends(get_db)):
    """Marks a match confirmed -- works on a previously rejected row too,
    so a user can change their mind."""
    match_repo = TransferMatchRepository(db)
    match = await match_repo.get(match_id)
    if not match:
        return {"error": "Match not found"}

    match.status = "confirmed"
    await match_repo.commit()

    return {"ok": True, "match": await _serialize_one(db, match)}


@router.post("/{match_id}/reject")
async def reject_transfer(match_id: int, db: AsyncSession = Depends(get_db)):
    """Unmatch: sets status="rejected" rather than deleting the row (D-06).
    The row becomes a durable tombstone that `scan_and_persist` consults via
    `rejected_pairs()`, so a subsequent scan can never resurrect a dismissed
    false positive. Because `_not_internal_transfer()` only excludes
    `confirmed` rows, both legs reappear in every report on the very next
    request -- there is no cache to invalidate."""
    match_repo = TransferMatchRepository(db)
    match = await match_repo.get(match_id)
    if not match:
        return {"error": "Match not found"}

    match.status = "rejected"
    await match_repo.commit()

    return {"ok": True, "match": await _serialize_one(db, match)}

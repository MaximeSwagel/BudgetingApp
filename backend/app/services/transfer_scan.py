"""Shared async orchestrator for internal-transfer detection.

This is the single entry point called both at the end of a successful CSV
upload (`app.routers.upload`) and by `POST /api/transfers/detect`
(`app.routers.transfers`), so there is exactly one copy of the scan-and-
persist wiring (D-07) -- an on-demand rescan and the automatic post-import
scan can never diverge.
"""

from app.models import InternalTransferMatch
from app.repositories import (
    CategoryGroupRepository,
    CategoryRepository,
    TransactionRepository,
    TransferMatchRepository,
)
from app.services.transfers import TransferLeg, match_transfers

TRANSFER_FEE_CATEGORY = "Transfer Fees"
TRANSFER_FEE_GROUP = "Insurance, Tax & Bank Fees"


async def resolve_transfer_fee_category_id(group_repo, category_repo) -> int | None:
    """Look up the Transfer Fees category id, or None when either the group
    or the category is missing. Callers must treat a None result as a soft
    failure -- a fee row then lands uncategorized rather than the whole
    upload failing."""
    group = await group_repo.get_by_name(TRANSFER_FEE_GROUP)
    if not group:
        return None
    category = await category_repo.get_by_name_in_group(TRANSFER_FEE_CATEGORY, group.id)
    return category.id if category else None


async def scan_and_persist(db) -> dict:
    """Fetch candidate transaction legs, run the pure matcher, and persist
    any new pairs as InternalTransferMatch rows: `status="confirmed"` for
    `high` confidence, `status="suggested"` otherwise (D-05). Idempotent --
    legs already claimed by an active match and pairs the user has already
    rejected are excluded from re-consideration by the matcher itself, so
    calling this twice in a row creates nothing new the second time."""
    txn_repo = TransactionRepository(db)
    match_repo = TransferMatchRepository(db)

    fee_category_id = await resolve_transfer_fee_category_id(
        CategoryGroupRepository(db), CategoryRepository(db)
    )

    rows = await txn_repo.list_transfer_candidates(exclude_category_id=fee_category_id)
    legs = [
        TransferLeg(
            id=row.id,
            date=row.date,
            description=row.description,
            original_amount=row.original_amount,
            original_currency=row.original_currency,
            converted_amount=row.converted_amount,
            bank=row.bank,
        )
        for row in rows
    ]

    already_matched_ids = await match_repo.active_leg_ids()
    rejected_pairs = await match_repo.rejected_pairs()

    pairs = match_transfers(legs, already_matched_ids=already_matched_ids, rejected_pairs=rejected_pairs)

    confirmed = 0
    suggested = 0
    for pair in pairs:
        status = "confirmed" if pair.confidence == "high" else "suggested"
        match_repo.add(
            InternalTransferMatch(
                outgoing_transaction_id=pair.outgoing_id,
                incoming_transaction_id=pair.incoming_id,
                confidence=pair.confidence,
                status=status,
            )
        )
        if status == "confirmed":
            confirmed += 1
        else:
            suggested += 1

    await match_repo.commit()

    return {
        "scanned": len(legs),
        "created": len(pairs),
        "confirmed": confirmed,
        "suggested": suggested,
    }

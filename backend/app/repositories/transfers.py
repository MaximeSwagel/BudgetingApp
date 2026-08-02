from sqlalchemy import delete, or_, select

from app.models import InternalTransferMatch
from app.repositories.base import BaseRepository


class TransferMatchRepository(BaseRepository[InternalTransferMatch]):
    model = InternalTransferMatch

    async def list_all(self) -> list[InternalTransferMatch]:
        """Every match, newest-detected first (ties broken by id descending)."""
        result = await self.db.execute(
            select(InternalTransferMatch).order_by(
                InternalTransferMatch.detected_at.desc(), InternalTransferMatch.id.desc()
            )
        )
        return list(result.scalars().all())

    async def active_leg_ids(self) -> set[int]:
        """Transaction ids already claimed by a confirmed or suggested match --
        consulted by a re-scan so a transaction is never matched twice."""
        result = await self.db.execute(
            select(
                InternalTransferMatch.outgoing_transaction_id,
                InternalTransferMatch.incoming_transaction_id,
            ).where(InternalTransferMatch.status.in_(["confirmed", "suggested"]))
        )
        ids: set[int] = set()
        for outgoing_id, incoming_id in result.all():
            ids.add(outgoing_id)
            ids.add(incoming_id)
        return ids

    async def rejected_pairs(self) -> set[tuple[int, int]]:
        """(outgoing_id, incoming_id) tuples the user has already dismissed --
        a tombstone so a re-scan never resurrects them (D-06)."""
        result = await self.db.execute(
            select(
                InternalTransferMatch.outgoing_transaction_id,
                InternalTransferMatch.incoming_transaction_id,
            ).where(InternalTransferMatch.status == "rejected")
        )
        return {(outgoing_id, incoming_id) for outgoing_id, incoming_id in result.all()}

    async def delete_for_transaction_ids(self, ids: set[int]) -> None:
        """Remove match rows referencing any of `ids` -- used by undo-import
        so a recycled transaction id can never inherit a stale exclusion (D-10)."""
        if not ids:
            return
        await self.db.execute(
            delete(InternalTransferMatch).where(
                or_(
                    InternalTransferMatch.outgoing_transaction_id.in_(ids),
                    InternalTransferMatch.incoming_transaction_id.in_(ids),
                )
            )
        )

    async def delete_all(self) -> None:
        """Used by /api/admin/reset."""
        await self.db.execute(delete(InternalTransferMatch))

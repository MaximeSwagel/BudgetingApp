from sqlalchemy import delete, func, or_, select

from app.models import ImportBatch, InternalTransferMatch, Transaction
from app.repositories.base import BaseRepository


class ImportBatchRepository(BaseRepository[ImportBatch]):
    model = ImportBatch

    async def delete_with_transactions(self, batch_id: int) -> int:
        """Undo an import: delete the batch's transactions and the batch row,
        plus any InternalTransferMatch rows referencing the removed
        transaction ids (D-10) -- otherwise a stale match row could
        silently exclude an unrelated future transaction that reuses a
        recycled id. Returns the number of transactions removed."""
        count_result = await self.db.execute(
            select(func.count()).select_from(Transaction).where(Transaction.import_batch_id == batch_id)
        )
        count = count_result.scalar() or 0

        ids_result = await self.db.execute(
            select(Transaction.id).where(Transaction.import_batch_id == batch_id)
        )
        transaction_ids = {row[0] for row in ids_result.all()}

        if transaction_ids:
            await self.db.execute(
                delete(InternalTransferMatch).where(
                    or_(
                        InternalTransferMatch.outgoing_transaction_id.in_(transaction_ids),
                        InternalTransferMatch.incoming_transaction_id.in_(transaction_ids),
                    )
                )
            )

        await self.db.execute(delete(Transaction).where(Transaction.import_batch_id == batch_id))
        await self.db.execute(delete(ImportBatch).where(ImportBatch.id == batch_id))
        await self.db.commit()
        return count

    async def delete_all_with_transactions(self) -> int:
        """Clear every transaction and import batch (categories/targets kept),
        along with every InternalTransferMatch row (D-10)."""
        count_result = await self.db.execute(select(func.count()).select_from(Transaction))
        count = count_result.scalar() or 0

        await self.db.execute(delete(InternalTransferMatch))
        await self.db.execute(delete(Transaction))
        await self.db.execute(delete(ImportBatch))
        await self.db.commit()
        return count

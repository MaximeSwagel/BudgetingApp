from sqlalchemy import delete, func, select

from app.models import ImportBatch, Transaction
from app.repositories.base import BaseRepository


class ImportBatchRepository(BaseRepository[ImportBatch]):
    model = ImportBatch

    async def delete_with_transactions(self, batch_id: int) -> int:
        """Undo an import: delete the batch's transactions and the batch row.
        Returns the number of transactions removed."""
        count_result = await self.db.execute(
            select(func.count()).select_from(Transaction).where(Transaction.import_batch_id == batch_id)
        )
        count = count_result.scalar() or 0

        await self.db.execute(delete(Transaction).where(Transaction.import_batch_id == batch_id))
        await self.db.execute(delete(ImportBatch).where(ImportBatch.id == batch_id))
        await self.db.commit()
        return count

    async def delete_all_with_transactions(self) -> int:
        """Clear every transaction and import batch (categories/targets kept)."""
        count_result = await self.db.execute(select(func.count()).select_from(Transaction))
        count = count_result.scalar() or 0

        await self.db.execute(delete(Transaction))
        await self.db.execute(delete(ImportBatch))
        await self.db.commit()
        return count

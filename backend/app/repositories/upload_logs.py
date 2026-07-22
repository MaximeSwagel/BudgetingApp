from sqlalchemy import select

from app.models import UploadLog
from app.repositories.base import BaseRepository


class UploadLogRepository(BaseRepository[UploadLog]):
    model = UploadLog

    async def list_recent(self, limit: int = 100) -> list[UploadLog]:
        """Newest-first audit trail of upload attempts, tie-broken by id so
        rows created within the same wall-clock tick still order deterministically."""
        result = await self.db.execute(
            select(UploadLog).order_by(UploadLog.uploaded_at.desc(), UploadLog.id.desc()).limit(limit)
        )
        return list(result.scalars().all())

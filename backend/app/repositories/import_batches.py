from app.models import ImportBatch
from app.repositories.base import BaseRepository


class ImportBatchRepository(BaseRepository[ImportBatch]):
    model = ImportBatch

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Common CRUD plumbing shared by all repositories.

    Every model-specific repository below is the single sanctioned place that
    builds queries against its table — routers should never call
    `select()`/`db.execute()` directly. Adding a column or relationship means
    updating the repository method that touches it, not hunting through routers.
    """

    model: type[ModelT]

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, id: int) -> ModelT | None:
        result = await self.db.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    def add(self, instance: ModelT) -> ModelT:
        self.db.add(instance)
        return instance

    async def flush(self) -> None:
        await self.db.flush()

    async def commit(self) -> None:
        await self.db.commit()

    async def refresh(self, instance: ModelT) -> None:
        await self.db.refresh(instance)

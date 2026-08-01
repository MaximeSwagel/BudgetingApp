from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models import Category, CategoryCorrection
from app.repositories.base import BaseRepository


class CategoryCorrectionRepository(BaseRepository[CategoryCorrection]):
    model = CategoryCorrection

    async def list_all(self) -> list[CategoryCorrection]:
        """Every correction, newest first. Eagerly loads category+group with
        chained joinedload -- touching `correction.category.group.name` on a
        lazily-loaded async relationship raises MissingGreenlet at runtime."""
        result = await self.db.execute(
            select(CategoryCorrection)
            .options(joinedload(CategoryCorrection.category).joinedload(Category.group))
            .order_by(CategoryCorrection.created_at.desc())
        )
        return list(result.scalars().unique().all())

    async def get_by_merchant_key(self, merchant_key: str) -> CategoryCorrection | None:
        result = await self.db.execute(
            select(CategoryCorrection)
            .options(joinedload(CategoryCorrection.category).joinedload(Category.group))
            .where(CategoryCorrection.merchant_key == merchant_key)
        )
        return result.scalar_one_or_none()

    async def key_map(self) -> dict[str, CategoryCorrection]:
        """merchant_key -> CategoryCorrection, eagerly loaded (see list_all)."""
        corrections = await self.list_all()
        return {c.merchant_key: c for c in corrections}

    async def remove(self, correction: CategoryCorrection) -> None:
        """BaseRepository has no delete -- kept local to this repository
        rather than widening the shared base for a single caller."""
        await self.db.delete(correction)

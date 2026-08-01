from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.models import Category, CategoryGroup
from app.repositories.base import BaseRepository


class CategoryGroupRepository(BaseRepository[CategoryGroup]):
    model = CategoryGroup

    async def list_with_categories(self) -> list[CategoryGroup]:
        result = await self.db.execute(
            select(CategoryGroup)
            .options(joinedload(CategoryGroup.categories))
            .order_by(CategoryGroup.display_order)
        )
        return list(result.scalars().unique().all())

    async def get_by_name(self, name: str) -> CategoryGroup | None:
        result = await self.db.execute(select(CategoryGroup).where(CategoryGroup.name == name))
        return result.scalar_one_or_none()

    async def remove(self, group: CategoryGroup) -> None:
        """BaseRepository has no delete -- kept local to this repository
        rather than widening the shared base for a single caller (see
        CategoryCorrectionRepository.remove for the same convention)."""
        await self.db.delete(group)


class CategoryRepository(BaseRepository[Category]):
    model = Category

    async def get_by_name_in_group(self, name: str, group_id: int) -> Category | None:
        result = await self.db.execute(
            select(Category).where(Category.name == name, Category.group_id == group_id)
        )
        return result.scalar_one_or_none()

    async def first_in_group(self, group_id: int) -> Category | None:
        result = await self.db.execute(select(Category).where(Category.group_id == group_id))
        return result.scalars().first()

    async def count_in_group(self, group_id: int) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(Category).where(Category.group_id == group_id)
        )
        return result.scalar() or 0

    async def remove(self, category: Category) -> None:
        """BaseRepository has no delete -- kept local to this repository."""
        await self.db.delete(category)

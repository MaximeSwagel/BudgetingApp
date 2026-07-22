from sqlalchemy import select

from app.models import BudgetTarget
from app.repositories.base import BaseRepository


class BudgetTargetRepository(BaseRepository[BudgetTarget]):
    model = BudgetTarget

    async def list_by_year(self, year: int) -> list[BudgetTarget]:
        result = await self.db.execute(select(BudgetTarget).where(BudgetTarget.year == year))
        return list(result.scalars().all())

    async def get_by_key(self, *, category_id: int, year: int, month: int) -> BudgetTarget | None:
        result = await self.db.execute(
            select(BudgetTarget).where(
                BudgetTarget.category_id == category_id,
                BudgetTarget.year == year,
                BudgetTarget.month == month,
            )
        )
        return result.scalar_one_or_none()

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.models import Category, CategoryGroup, Transaction
from app.repositories.base import BaseRepository


class TransactionRepository(BaseRepository[Transaction]):
    model = Transaction

    async def list_filtered(
        self,
        *,
        bank: str | None = None,
        currency: str | None = None,
        category_group: str | None = None,
        category: str | None = None,
        uncategorized: bool = False,
        date_from: str | None = None,
        date_to: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Transaction], int]:
        query = (
            select(Transaction)
            .options(joinedload(Transaction.category).joinedload(Category.group))
            .where(Transaction.is_duplicate == False)  # noqa: E712
        )

        if bank:
            query = query.where(Transaction.bank == bank)
        if currency:
            query = query.where(Transaction.original_currency == currency)
        if date_from:
            query = query.where(Transaction.date >= date_from)
        if date_to:
            query = query.where(Transaction.date <= date_to)
        if category_group:
            query = query.join(Transaction.category).join(Category.group).where(
                CategoryGroup.name == category_group
            )
        if category:
            query = query.join(Transaction.category, isouter=True).where(Category.name == category)
        if uncategorized:
            query = query.where(Transaction.category_id.is_(None))

        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        query = query.order_by(Transaction.date.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        transactions = list(result.scalars().unique().all())

        return transactions, total

    async def find_duplicate(
        self,
        *,
        date: datetime,
        amount: Decimal,
        currency: str,
        bank: str,
        description: str,
    ) -> Transaction | None:
        result = await self.db.execute(
            select(Transaction).where(
                Transaction.date == date,
                Transaction.original_amount == amount,
                Transaction.original_currency == currency,
                Transaction.bank == bank,
                Transaction.description == description,
            )
        )
        return result.scalar_one_or_none()

    async def list_uncategorized(self, limit: int = 300) -> list[Transaction]:
        result = await self.db.execute(
            select(Transaction)
            .where(
                Transaction.category_id.is_(None),
                Transaction.is_duplicate == False,  # noqa: E712
            )
            .order_by(Transaction.date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_uncategorized(self) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.category_id.is_(None),
                Transaction.is_duplicate == False,  # noqa: E712
            )
        )
        return result.scalar() or 0

    async def monthly_totals_since(self, since: datetime):
        """(year, month, is_expense, total) rows for all non-duplicate
        transactions on/after `since`, in base-currency converted amounts."""
        from sqlalchemy import extract

        result = await self.db.execute(
            select(
                extract("year", Transaction.date).label("year"),
                extract("month", Transaction.date).label("month"),
                Transaction.is_expense,
                func.sum(Transaction.converted_amount).label("total"),
            )
            .where(
                Transaction.date >= since,
                Transaction.is_duplicate == False,  # noqa: E712
            )
            .group_by("year", "month", Transaction.is_expense)
        )
        return result.all()

    async def group_totals_for_month(self, year: int, month: int):
        """(group_name, total) expense rows for one month, largest first."""
        from sqlalchemy import extract

        result = await self.db.execute(
            select(
                CategoryGroup.name.label("group_name"),
                func.sum(Transaction.converted_amount).label("total"),
            )
            .join(Transaction.category)
            .join(Category.group)
            .where(
                extract("year", Transaction.date) == year,
                extract("month", Transaction.date) == month,
                Transaction.is_expense == True,  # noqa: E712
                Transaction.is_duplicate == False,  # noqa: E712
            )
            .group_by("group_name")
        )
        return result.all()

    async def monthly_category_totals(self, year: int):
        from sqlalchemy import extract

        result = await self.db.execute(
            select(
                extract("month", Transaction.date).label("month"),
                CategoryGroup.name.label("group_name"),
                Category.name.label("category_name"),
                func.sum(Transaction.converted_amount).label("total"),
            )
            .join(Transaction.category)
            .join(Category.group)
            .where(
                extract("year", Transaction.date) == year,
                Transaction.is_expense == True,  # noqa: E712
                Transaction.is_duplicate == False,  # noqa: E712
            )
            .group_by("month", "group_name", "category_name")
            .order_by("group_name", "category_name", "month")
        )
        return result.all()

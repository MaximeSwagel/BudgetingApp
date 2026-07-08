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

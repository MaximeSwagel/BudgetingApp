from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select

from app.models import CategoryGroupTarget
from app.repositories.base import BaseRepository


def _latest_at(rows: list[CategoryGroupTarget], at: date) -> CategoryGroupTarget | None:
    """Given ROWS pre-sorted ascending by `effective_month`, returns the
    last row whose `effective_month <= at`, or None if none qualify.

    This is the single fold both `effective_targets_for_year` and
    `effective_targets_at` build on, so the "greatest effective_month <=
    the month being rendered" rule (see `CategoryGroupTarget`'s docstring)
    has exactly one implementation.
    """
    latest: CategoryGroupTarget | None = None
    for row in rows:
        if row.effective_month <= at:
            latest = row
        else:
            break
    return latest


class CategoryGroupTargetRepository(BaseRepository[CategoryGroupTarget]):
    model = CategoryGroupTarget

    async def list_all(self) -> list[CategoryGroupTarget]:
        """Every row, ordered by group then effective_month. The table has
        at most a handful of rows per group, so the effective-dating fold
        happens in Python (via `_latest_at`) rather than as a correlated
        SQL subquery -- this also sidesteps the SQLite-vs-Postgres
        date-typing divergences already documented in TransactionRepository.
        """
        result = await self.db.execute(
            select(CategoryGroupTarget).order_by(
                CategoryGroupTarget.group_id, CategoryGroupTarget.effective_month
            )
        )
        return list(result.scalars().all())

    async def get_by_group_and_month(
        self, *, group_id: int, effective_month: date
    ) -> CategoryGroupTarget | None:
        result = await self.db.execute(
            select(CategoryGroupTarget).where(
                CategoryGroupTarget.group_id == group_id,
                CategoryGroupTarget.effective_month == effective_month,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_for_month(
        self, *, group_id: int, amount: Decimal | None, effective_month: date
    ) -> CategoryGroupTarget:
        """Fetches the row for (group_id, effective_month); updates its
        amount in place if found (including setting it to None), otherwise
        adds a new row. Does not commit -- the caller commits."""
        existing = await self.get_by_group_and_month(
            group_id=group_id, effective_month=effective_month
        )
        if existing is not None:
            existing.amount = amount
            return existing

        return self.add(
            CategoryGroupTarget(
                group_id=group_id, amount=amount, effective_month=effective_month
            )
        )

    async def effective_targets_for_year(self, year: int) -> dict[int, dict[int, Decimal | None]]:
        """`{group_id: {1..12: Decimal | None}}` over every group that has
        at least one row, applying the effective-dating rule."""
        rows = await self.list_all()
        by_group: dict[int, list[CategoryGroupTarget]] = {}
        for row in rows:
            by_group.setdefault(row.group_id, []).append(row)

        result: dict[int, dict[int, Decimal | None]] = {}
        for group_id, group_rows in by_group.items():
            months: dict[int, Decimal | None] = {}
            for month in range(1, 13):
                latest = _latest_at(group_rows, date(year, month, 1))
                months[month] = latest.amount if latest is not None else None
            result[group_id] = months
        return result

    async def effective_targets_at(self, on_month: date) -> dict[int, Decimal | None]:
        """The effective amount per group at a single month-start, used for
        `current_target`."""
        rows = await self.list_all()
        by_group: dict[int, list[CategoryGroupTarget]] = {}
        for row in rows:
            by_group.setdefault(row.group_id, []).append(row)

        return {
            group_id: (latest.amount if (latest := _latest_at(group_rows, on_month)) is not None else None)
            for group_id, group_rows in by_group.items()
        }

    async def delete_by_group(self, group_id: int) -> None:
        """Called when a CategoryGroup is deleted: its targets are planning
        metadata meaningless without the group, and would otherwise dangle
        under Postgres (SQLite in tests does not enforce FKs)."""
        await self.db.execute(
            delete(CategoryGroupTarget).where(CategoryGroupTarget.group_id == group_id)
        )

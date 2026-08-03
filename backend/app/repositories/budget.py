from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select

from app.models import CategoryGroupTarget
from app.repositories.base import BaseRepository


def _latest(rows: list[CategoryGroupTarget]) -> CategoryGroupTarget | None:
    """Given ROWS pre-sorted ascending by `effective_month`, returns the
    single overall-latest row -- the group's current target, full stop, no
    date comparison against a rendered month. `rows[-1]` when non-empty,
    otherwise `None`. The unique constraint on `(group_id, effective_month)`
    guarantees there is never a tie for "latest". `effective_month` is kept
    on the row for a possible future per-month/versioned read mode -- it is
    not consulted here.
    """
    return rows[-1] if rows else None


class CategoryGroupTargetRepository(BaseRepository[CategoryGroupTarget]):
    model = CategoryGroupTarget

    async def list_all(self) -> list[CategoryGroupTarget]:
        """Every row, ordered by group then effective_month. The table has
        at most a handful of rows per group, so resolving "the latest row"
        happens in Python (via `_latest`) rather than as a correlated SQL
        subquery -- this also sidesteps the SQLite-vs-Postgres date-typing
        divergences already documented in TransactionRepository.
        """
        result = await self.db.execute(
            select(CategoryGroupTarget).order_by(
                CategoryGroupTarget.group_id, CategoryGroupTarget.effective_month
            )
        )
        return list(result.scalars().all())

    def _by_group(
        self, rows: list[CategoryGroupTarget]
    ) -> dict[int, list[CategoryGroupTarget]]:
        """Buckets `list_all()` output into `{group_id: [rows...]}` --
        shared by both read methods below."""
        by_group: dict[int, list[CategoryGroupTarget]] = {}
        for row in rows:
            by_group.setdefault(row.group_id, []).append(row)
        return by_group

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

    async def current_targets_by_month(self) -> dict[int, dict[int, Decimal | None]]:
        """`{group_id: {1..12: Decimal | None}}` over every group that has
        at least one row. Each group's newest row is its target -- the same
        value is assigned to all 12 months; there is no per-month split."""
        by_group = self._by_group(await self.list_all())

        result: dict[int, dict[int, Decimal | None]] = {}
        for group_id, group_rows in by_group.items():
            latest = _latest(group_rows)
            amount = latest.amount if latest is not None else None
            result[group_id] = {month: amount for month in range(1, 13)}
        return result

    async def current_targets(self) -> dict[int, Decimal | None]:
        """The single current amount per group (each group's newest row),
        used for `current_target`."""
        by_group = self._by_group(await self.list_all())

        return {
            group_id: (latest.amount if (latest := _latest(group_rows)) is not None else None)
            for group_id, group_rows in by_group.items()
        }

    async def delete_by_group(self, group_id: int) -> None:
        """Called when a CategoryGroup is deleted: its targets are planning
        metadata meaningless without the group, and would otherwise dangle
        under Postgres (SQLite in tests does not enforce FKs)."""
        await self.db.execute(
            delete(CategoryGroupTarget).where(CategoryGroupTarget.group_id == group_id)
        )

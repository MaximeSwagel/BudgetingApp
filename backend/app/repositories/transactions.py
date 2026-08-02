from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from app.models import Category, CategoryGroup, InternalTransferMatch, Transaction
from app.repositories.base import BaseRepository


def _not_internal_transfer():
    """A tuple of two `NOT IN` conditions -- spread with
    `.where(*_not_internal_transfer())` -- that excludes both legs of a
    CONFIRMED internal transfer match, exactly the way `is_duplicate` rows
    are excluded everywhere. `suggested` and `rejected` rows are
    deliberately NOT excluded here (D-05/D-06): only a `confirmed` pair is
    considered settled enough to disappear from every report.

    Two separate `NOT IN` subqueries (one per id column) are used
    deliberately instead of a single `UNION` subquery: this codebase runs
    SQLite in tests and Postgres at runtime and already carries several
    dialect-divergence workarounds, and a plain `NOT IN` against a single
    column is the form with no dialect risk. Both id columns are
    `nullable=False`, so there is no `NOT IN` NULL trap.

    Deliberately NOT applied to `find_duplicate` (import-time dedup must
    see every row, including hidden legs, or a re-upload would insert a
    second copy), nor to `list_matching_candidates`, `count_by_category`,
    or the inherited `get` -- a future reader should not "fix" that
    omission.
    """
    confirmed_outgoing = select(InternalTransferMatch.outgoing_transaction_id).where(
        InternalTransferMatch.status == "confirmed"
    )
    confirmed_incoming = select(InternalTransferMatch.incoming_transaction_id).where(
        InternalTransferMatch.status == "confirmed"
    )
    return (
        Transaction.id.notin_(confirmed_outgoing),
        Transaction.id.notin_(confirmed_incoming),
    )


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
        include_transfers: bool = False,
    ) -> tuple[list[Transaction], int]:
        query = (
            select(Transaction)
            .options(joinedload(Transaction.category).joinedload(Category.group))
            .where(Transaction.is_duplicate == False)  # noqa: E712
        )
        if not include_transfers:
            query = query.where(*_not_internal_transfer())

        if bank:
            query = query.where(Transaction.bank == bank)
        if currency:
            query = query.where(Transaction.original_currency == currency)
        # date_from/date_to arrive as "YYYY-MM-DD" strings from an HTML
        # <input type="date">. `Transaction.date` is a DateTime column, so
        # these must be parsed into real datetime boundaries before being
        # bound as query params -- comparing a DateTime column directly
        # against a raw string works "by accident" under SQLite (weak
        # column typing) but raises `UndefinedFunctionError: operator does
        # not exist: timestamp >= character varying` under PostgreSQL,
        # which is the actual DB used in docker-compose. date_to is treated
        # as inclusive of the whole day (< next midnight), not an exact
        # midnight cutoff, so same-day transactions with a time component
        # aren't silently dropped.
        if date_from:
            query = query.where(
                Transaction.date >= datetime.combine(date.fromisoformat(date_from), time.min)
            )
        if date_to:
            query = query.where(
                Transaction.date < datetime.combine(date.fromisoformat(date_to), time.min) + timedelta(days=1)
            )
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

    async def list_by_ids(self, ids: set[int]) -> list[Transaction]:
        """Transactions for a set of ids, eagerly loading category+group --
        touching `txn.category.group.name` on a lazily-loaded async
        relationship raises MissingGreenlet (see
        CategoryCorrectionRepository.list_all for the same convention).
        Used by the Internal Transfers router to fetch both legs of every
        match in one query rather than N+1 `get()` calls."""
        if not ids:
            return []
        result = await self.db.execute(
            select(Transaction)
            .options(joinedload(Transaction.category).joinedload(Category.group))
            .where(Transaction.id.in_(ids))
        )
        return list(result.scalars().unique().all())

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

    async def list_income(self, limit: int = 5000) -> list[Transaction]:
        """All non-duplicate income transactions (is_expense == False), oldest
        first. No Category join -- income never has a category_id (see
        app.services.income). `limit` is a pure safety bound, not a real page
        size: income volume is low by definition, which is the entire premise
        of the recurring-stream detector that consumes this."""
        result = await self.db.execute(
            select(Transaction)
            .where(
                Transaction.is_expense == False,  # noqa: E712
                Transaction.is_duplicate == False,  # noqa: E712
            )
            .order_by(Transaction.date.asc(), Transaction.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_matching_candidates(self, first_token: str, limit: int = 1000) -> list[Transaction]:
        """Cheap SQL pre-filter for retroactive merchant corrections: a
        case-insensitive `ilike` wildcard on `first_token`, bounded by
        `limit`. The merchant key is normalized (punctuation and digits
        stripped) so it may not appear verbatim in the raw description --
        the caller MUST re-verify each candidate in Python with `match_key`.
        This is not the authoritative match, just a bounded scan surface."""
        result = await self.db.execute(
            select(Transaction)
            .where(
                Transaction.description.ilike(f"%{first_token}%"),
                Transaction.is_duplicate == False,  # noqa: E712
            )
            .limit(limit)
        )
        return list(result.scalars().all())

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
                *_not_internal_transfer(),
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
                *_not_internal_transfer(),
            )
            .group_by("group_name")
        )
        return result.all()

    async def daily_category_spend(self, since: datetime, exclude_ids: set[int] | None = None):
        """(day, category_name, total) expense rows on/after `since`, in base-
        currency converted amounts. `category_name` is None for uncategorized
        rows (outer join keeps them instead of dropping them). `exclude_ids`,
        when given a non-empty set, drops those transaction ids from the
        aggregate -- used by the Analysis page's "exclude recurring large
        expenses" toggle."""
        query = (
            select(
                func.date(Transaction.date).label("day"),
                Category.name.label("category_name"),
                func.sum(Transaction.converted_amount).label("total"),
            )
            .join(Transaction.category, isouter=True)
            .where(
                Transaction.is_expense == True,  # noqa: E712
                Transaction.is_duplicate == False,  # noqa: E712
                Transaction.date >= since,
                *_not_internal_transfer(),
            )
        )
        if exclude_ids:
            query = query.where(Transaction.id.notin_(exclude_ids))
        result = await self.db.execute(query.group_by("day", "category_name").order_by("day"))
        return result.all()

    async def category_distribution(self, exclude_ids: set[int] | None = None):
        """(group_name, category_name, total, count) expense rows, largest
        total first is left to the caller -- this returns unsorted groups.
        See `daily_category_spend` for `exclude_ids`."""
        query = (
            select(
                CategoryGroup.name.label("group_name"),
                Category.name.label("category_name"),
                func.sum(Transaction.converted_amount).label("total"),
                func.count().label("count"),
            )
            .join(Transaction.category)
            .join(Category.group)
            .where(
                Transaction.is_expense == True,  # noqa: E712
                Transaction.is_duplicate == False,  # noqa: E712
                *_not_internal_transfer(),
            )
        )
        if exclude_ids:
            query = query.where(Transaction.id.notin_(exclude_ids))
        result = await self.db.execute(query.group_by("group_name", "category_name"))
        return result.all()

    async def currency_breakdown(self, exclude_ids: set[int] | None = None):
        """(original_currency, original_total, converted_total, count) rows,
        pre-conversion sign preserved (not abs'd), across all non-duplicate
        transactions. See `daily_category_spend` for `exclude_ids`."""
        query = select(
            Transaction.original_currency,
            func.sum(Transaction.original_amount).label("original_total"),
            func.sum(Transaction.converted_amount).label("converted_total"),
            func.count().label("count"),
        ).where(Transaction.is_duplicate == False, *_not_internal_transfer())  # noqa: E712
        if exclude_ids:
            query = query.where(Transaction.id.notin_(exclude_ids))
        result = await self.db.execute(query.group_by(Transaction.original_currency))
        return result.all()

    async def bank_breakdown(self, exclude_ids: set[int] | None = None) -> list[dict]:
        """(bank, count, total) rows across all non-duplicate transactions,
        total is the sum of absolute converted amounts (volume moved through
        that source, income and expense alike). Aggregated in Python rather
        than `func.sum(func.abs(...))`: SQLite loses the Numeric column's
        Decimal typing through `func.abs()`, returning e.g. "30" instead of
        "30.00" and breaking the app's string-money convention. See
        `daily_category_spend` for `exclude_ids`."""
        result = await self.db.execute(
            select(Transaction.id, Transaction.bank, Transaction.converted_amount).where(
                Transaction.is_duplicate == False,  # noqa: E712
                *_not_internal_transfer(),
            )
        )
        rows = result.all()

        totals: dict[str, dict] = {}
        for row in rows:
            if exclude_ids and row.id in exclude_ids:
                continue
            bucket = totals.setdefault(row.bank, {"count": 0, "total": Decimal("0")})
            bucket["count"] += 1
            bucket["total"] += abs(row.converted_amount or Decimal("0"))

        return [
            {"bank": bank, "count": bucket["count"], "total": bucket["total"]}
            for bank, bucket in totals.items()
        ]

    async def list_expense_rows_for_recurring(self):
        """(id, description, date, converted_amount, category_name,
        group_name) rows for every non-duplicate expense transaction with a
        converted amount -- raw material for recurring-merchant detection
        (see app.services.recurring), which needs individual transactions
        rather than a pre-aggregated total."""
        result = await self.db.execute(
            select(
                Transaction.id,
                Transaction.description,
                Transaction.date,
                Transaction.converted_amount,
                Category.name.label("category_name"),
                CategoryGroup.name.label("group_name"),
            )
            .join(Transaction.category, isouter=True)
            .join(Category.group, isouter=True)
            .where(
                Transaction.is_expense == True,  # noqa: E712
                Transaction.is_duplicate == False,  # noqa: E712
                Transaction.converted_amount.isnot(None),
                *_not_internal_transfer(),
            )
        )
        return result.all()

    async def list_transfer_candidates(self, exclude_category_id: int | None = None):
        """(id, date, description, original_amount, original_currency,
        converted_amount, bank, category_id) rows -- raw material for
        internal-transfer detection (see app.services.transfers /
        app.services.transfer_scan). `exclude_category_id`, when given,
        drops rows already categorized under it so a synthesized Transfer
        Fees row can never itself become a transfer leg."""
        query = select(
            Transaction.id,
            Transaction.date,
            Transaction.description,
            Transaction.original_amount,
            Transaction.original_currency,
            Transaction.converted_amount,
            Transaction.bank,
            Transaction.category_id,
        ).where(
            Transaction.is_duplicate == False,  # noqa: E712
            Transaction.converted_amount.isnot(None),
        )
        if exclude_category_id is not None:
            query = query.where(
                or_(
                    Transaction.category_id.is_(None),
                    Transaction.category_id != exclude_category_id,
                )
            )
        result = await self.db.execute(query)
        return result.all()

    async def duplicate_groups(self) -> list[dict]:
        """Groups of non-duplicate transactions sharing (day, original_amount,
        description) with count > 1 -- a looser integrity check than the
        strict 5-tuple import-time dedup (see analysis router docstring).
        Aggregated in Python (not SQL GROUP BY + HAVING) to stay portable
        across SQLite (tests) and Postgres without dialect-specific date
        comparisons."""
        result = await self.db.execute(
            select(
                Transaction.date,
                Transaction.original_amount,
                Transaction.description,
                Transaction.bank,
            ).where(Transaction.is_duplicate == False, *_not_internal_transfer())  # noqa: E712
        )
        rows = result.all()

        buckets: dict[tuple, dict] = {}
        for row in rows:
            key = (row.date.date(), row.original_amount, row.description)
            bucket = buckets.setdefault(key, {"banks": set(), "count": 0})
            bucket["banks"].add(row.bank)
            bucket["count"] += 1

        return [
            {
                "day": day,
                "amount": amount,
                "description": description,
                "count": bucket["count"],
                "banks": sorted(bucket["banks"]),
            }
            for (day, amount, description), bucket in buckets.items()
            if bucket["count"] > 1
        ]

    async def count_by_category(self, category_id: int) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(Transaction).where(Transaction.category_id == category_id)
        )
        return result.scalar() or 0

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
                *_not_internal_transfer(),
            )
            .group_by("month", "group_name", "category_name")
            .order_by("group_name", "category_name", "month")
        )
        return result.all()

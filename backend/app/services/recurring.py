"""Recurring large-expense detection.

Groups non-duplicate expense transactions by merchant (via
`normalize_merchant`) and flags merchants that recur across at least
MIN_MONTHS distinct calendar months with a typical per-month amount at/above
`threshold`. Each detected group carries a `status` describing how the
latest month's amount compares to the merchant's prior baseline, plus an
`overdue` flag when the merchant hasn't shown up recently relative to its
own historical cadence -- together these are the "warning if these big
expenses change" signal surfaced on the Analysis page.

Purely computed at read time from existing transaction rows: no new tables,
no migration, no persisted "recurring" state to keep in sync with edits/
undo-import. Recomputing on every request is cheap at personal-budget-app
scale (a few thousand transactions).
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from statistics import median

from app.services.corrections import normalize_merchant

# Config key under which the user-configurable threshold is persisted in
# UserSettings; shared by the analysis and settings routers.
RECURRING_THRESHOLD_KEY = "recurring_large_threshold"

# A merchant must appear in at least this many distinct calendar months to
# be considered "recurring" rather than a one-off large purchase.
MIN_MONTHS = 3

# Latest-month amount vs. baseline median beyond this fraction is flagged as
# "increased"/"decreased" rather than "stable".
CHANGE_TOLERANCE = Decimal("0.15")

# A merchant is "overdue" once this many times its own average cadence has
# elapsed since its last occurrence, e.g. a monthly subscription silent for
# 45+ days (1.5x a ~30 day cadence) may have lapsed, changed merchant name,
# or been missed -- worth a look either way.
OVERDUE_MULTIPLIER = 1.5

# Fallback cadence (days) when a merchant has exactly MIN_MONTHS occurrences
# and therefore only one inter-occurrence gap is unreliable; monthly is the
# overwhelmingly common case for rent/subscriptions this feature targets.
DEFAULT_CADENCE_DAYS = 30


@dataclass
class TxnRow:
    id: int
    description: str
    date: datetime
    amount: Decimal  # abs(converted_amount), base currency
    category_name: str | None
    group_name: str | None


@dataclass
class RecurringGroup:
    merchant_key: str
    description: str
    category: str | None
    group: str | None
    occurrences: list[dict] = field(default_factory=list)  # [{month, amount}], oldest first
    transaction_ids: list[int] = field(default_factory=list)
    latest_amount: Decimal = Decimal("0")
    baseline_amount: Decimal = Decimal("0")
    pct_change: Decimal | None = None
    status: str = "stable"  # stable | increased | decreased
    overdue: bool = False
    last_seen: datetime | None = None


def detect_recurring_large_expenses(
    rows: list[TxnRow],
    threshold: Decimal,
    as_of: datetime | None = None,
) -> list[RecurringGroup]:
    """Returns recurring large-expense groups, largest latest amount first."""
    as_of = as_of or datetime.utcnow()

    by_merchant: dict[str, list[TxnRow]] = {}
    for row in rows:
        key = normalize_merchant(row.description)
        if not key:
            continue
        by_merchant.setdefault(key, []).append(row)

    groups: list[RecurringGroup] = []
    for key, txns in by_merchant.items():
        by_month: dict[tuple[int, int], list[TxnRow]] = {}
        for t in txns:
            by_month.setdefault((t.date.year, t.date.month), []).append(t)

        if len(by_month) < MIN_MONTHS:
            continue

        # Multiple charges from the same merchant in one calendar month
        # (e.g. two Amazon orders) are summed into that month's figure --
        # a deliberate simplification, not cadence-aware line-item matching.
        months_sorted = sorted(by_month.keys())
        month_amounts = [
            sum((t.amount for t in by_month[m]), Decimal("0")) for m in months_sorted
        ]

        # Gate on the *typical* month, not every month -- a merchant that's
        # usually large but had one prorated/partial month should still
        # qualify (and the dip itself may be exactly the kind of change
        # worth warning about).
        if median(month_amounts) < threshold:
            continue

        latest_amount = month_amounts[-1]
        baseline_pool = month_amounts[:-1]
        baseline_amount = median(baseline_pool) if baseline_pool else latest_amount

        pct_change: Decimal | None = None
        status = "stable"
        if baseline_amount > 0:
            pct_change = (latest_amount - baseline_amount) / baseline_amount
            if pct_change > CHANGE_TOLERANCE:
                status = "increased"
            elif pct_change < -CHANGE_TOLERANCE:
                status = "decreased"

        anchor_dates = [max(t.date for t in by_month[m]) for m in months_sorted]
        gaps = [(anchor_dates[i] - anchor_dates[i - 1]).days for i in range(1, len(anchor_dates))]
        avg_cadence = (sum(gaps) / len(gaps)) if gaps else DEFAULT_CADENCE_DAYS
        last_seen = anchor_dates[-1]
        days_since = (as_of - last_seen).days
        overdue = days_since > avg_cadence * OVERDUE_MULTIPLIER

        latest_txn = max(txns, key=lambda t: t.date)

        groups.append(
            RecurringGroup(
                merchant_key=key,
                description=latest_txn.description,
                category=latest_txn.category_name,
                group=latest_txn.group_name,
                occurrences=[
                    {"month": f"{y:04d}-{m:02d}", "amount": str(amt)}
                    for (y, m), amt in zip(months_sorted, month_amounts)
                ],
                transaction_ids=[t.id for t in txns],
                latest_amount=latest_amount,
                baseline_amount=baseline_amount,
                pct_change=pct_change,
                status=status,
                overdue=overdue,
                last_seen=last_seen,
            )
        )

    groups.sort(key=lambda g: g.latest_amount, reverse=True)
    return groups

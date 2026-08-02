"""Recurring-income stream detection and the Income page's report payload.

Purely computed, DB-free, and `today`-injected (J-07): this module never
imports `sqlalchemy` and never calls `date.today()` / `datetime.utcnow()`.
The caller (the income router) resolves ORM rows into `IncomeRow` and passes
`today` explicitly, which is what makes the whole status ladder unit-testable
with constructed dates and no freezegun dependency.

Implements Steps 1-6 of the recurring-detection algorithm documented in the
plan (see judgment calls J-01 through J-12 for the rationale behind each
constant/threshold below):

1. Bucket income rows by (bank, normalized merchant).
2. Split each bucket into amount-cohesive clusters (walked in date order).
3. Infer a named cadence from the median day-gap of a cluster with n >= 3.
4. Gate on regularity: >= 75% of gaps must conform to the cadence's period.
5. Predict the next occurrence and derive a status (upcoming/due/late/
   missing/ended), plus the latest-vs-previous amount delta.
6. Assemble: recognized clusters become streams; everything else (including
   the ungroupable empty-key rows from step 1) becomes a one-off.

No persistence, no schema change, no migration (J-09) -- streams are derived
fresh on every call.
"""

import calendar
import hashlib
import math
import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.services.corrections import normalize_merchant

# J-03: two payments are a coincidence; three establish a cadence (two gaps
# to compare). Below this, evidence is too thin to claim a cadence.
MIN_OCCURRENCES = 3

# J-02: amount cohesion tolerance -- 25% of the running cluster median, with
# an absolute floor so percentage math doesn't split small recurring amounts.
AMOUNT_TOLERANCE_PCT = Decimal("0.25")
AMOUNT_TOLERANCE_ABS = Decimal("50")

# J-04: cadence is recognized only from a named window (median day-gap ->
# cadence/label/canonical period_days). Anything else is "irregular" and the
# cluster's rows fall back to one-offs rather than inventing a fake cadence.
CADENCE_WINDOWS: list[tuple[int, int, str, str, int]] = [
    (6, 8, "weekly", "Weekly", 7),
    (12, 16, "biweekly", "Every 2 weeks", 14),
    (26, 35, "monthly", "Monthly", 30),
    (55, 70, "bimonthly", "Every 2 months", 61),
    (80, 100, "quarterly", "Quarterly", 91),
]

# J-05: a cluster is a recognized stream only if at least this fraction of
# its gaps conform (within tolerance) to the canonical period.
REGULARITY_MIN_RATIO = 0.75

# Used to normalize any recognized cadence into a comparable monthly figure
# for `recurring_monthly_estimate` (average days in a Gregorian month).
MONTH_DAYS_AVG = Decimal("30.44")

TWO_PLACES = Decimal("0.01")
ONE_PLACE = Decimal("0.1")

# J-06: statuses whose streams need attention first when sorting.
_PRIORITY_STATUSES = {"missing", "late"}


@dataclass
class IncomeRow:
    """One income transaction, already resolved to the module's needs.

    `amount` is the J-08 amount basis (converted_amount when not None, else
    original_amount, magnitude via abs()) -- the value clustering, cadence,
    and totals are computed from. `original_amount`/`original_currency` are
    passed through unabsorbed/unconverted purely for display.
    """

    id: int
    date: date
    description: str
    bank: str
    amount: Decimal
    original_amount: Decimal
    original_currency: str


@dataclass
class _Stream:
    """Internal representation of a recognized recurring stream, carrying
    raw Decimal/date values -- serialized to the public dict shape by
    `_serialize_stream` only at the very end, after sorting."""

    id: str
    label: str
    bank: str
    cadence: str
    cadence_label: str
    period_days: int
    tolerance_days: int
    first_date: date
    last_date: date
    expected_next: date
    status: str
    overdue_days: int
    latest_amount: Decimal
    previous_amount: Decimal
    delta: Decimal
    delta_pct: Decimal | None
    median_amount: Decimal
    total_amount: Decimal
    occurrences: list[IncomeRow]


def _tolerance_days(period_days: int) -> int:
    """J-05: `max(ceil(0.25 * period_days), 3)`."""
    return max(math.ceil(0.25 * period_days), 3)


def _cluster_by_amount(rows: list[IncomeRow]) -> list[list[IncomeRow]]:
    """Step 2: walk `rows` (already in date order) into amount-cohesive
    clusters. A row joins the current cluster when it's within tolerance of
    the median of the amounts already in that cluster; otherwise it starts a
    new cluster. Never discards a row, and never revisits a closed cluster
    (J-02) -- this is a single greedy forward pass."""
    clusters: list[list[IncomeRow]] = []
    for row in rows:
        if clusters:
            current = clusters[-1]
            current_median = statistics.median(r.amount for r in current)
            tolerance = max(current_median * AMOUNT_TOLERANCE_PCT, AMOUNT_TOLERANCE_ABS)
            if abs(row.amount - current_median) <= tolerance:
                current.append(row)
                continue
        clusters.append([row])
    return clusters


def _infer_cadence(median_gap: float) -> tuple[str, str, int] | None:
    """Step 3 (J-04): snap a median day-gap to a named cadence window, or
    None when it falls in no recognized window ("irregular")."""
    for low, high, cadence, label, period_days in CADENCE_WINDOWS:
        if low <= median_gap <= high:
            return cadence, label, period_days
    return None


def _is_regular(gaps: list[int], period_days: int) -> bool:
    """Step 4 (J-05): True when >= REGULARITY_MIN_RATIO of `gaps` conform
    (within `_tolerance_days(period_days)`) to `period_days`."""
    if not gaps:
        return False
    tolerance = _tolerance_days(period_days)
    conforming = sum(1 for gap in gaps if abs(gap - period_days) <= tolerance)
    return (conforming / len(gaps)) >= REGULARITY_MIN_RATIO


def _add_months(d: date, months: int) -> date:
    """J-10: calendar-aware month stepping (positive or negative), clamping
    the day-of-month to the target month's length via `calendar.monthrange`
    (e.g. Jan 31 + 1 month -> Feb 28/29). Stdlib only, no `dateutil`."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _expected_next(last_date: date, cadence: str, period_days: int) -> date:
    """Step 5: the next occurrence after `last_date` for a recognized
    cadence. Weekly/biweekly step by a fixed timedelta; monthly/bimonthly/
    quarterly step by calendar months (J-10)."""
    if cadence == "weekly":
        return last_date + timedelta(days=7)
    if cadence == "biweekly":
        return last_date + timedelta(days=14)
    if cadence == "monthly":
        return _add_months(last_date, 1)
    if cadence == "bimonthly":
        return _add_months(last_date, 2)
    if cadence == "quarterly":
        return _add_months(last_date, 3)
    raise ValueError(f"unrecognized cadence: {cadence!r}")  # pragma: no cover - guarded by CADENCE_WINDOWS


def _status_for(overdue_days: int, tolerance_days: int, period_days: int) -> str:
    """Step 5 (J-06): the upcoming -> due -> late -> missing -> ended
    ladder, driven purely by how overdue the expected next occurrence is."""
    if overdue_days < -tolerance_days:
        return "upcoming"
    if overdue_days <= tolerance_days:
        return "due"
    if overdue_days <= period_days:
        return "late"
    if overdue_days <= 2 * period_days:
        return "missing"
    return "ended"


def _prev_month(d: date) -> tuple[int, int]:
    if d.month == 1:
        return d.year - 1, 12
    return d.year, d.month - 1


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _serialize_occurrence(row: IncomeRow) -> dict:
    return {
        "id": row.id,
        "date": row.date.isoformat(),
        "amount": str(row.amount.quantize(TWO_PLACES)),
        "original_amount": str(row.original_amount.quantize(TWO_PLACES)),
        "original_currency": row.original_currency,
        "description": row.description,
        "bank": row.bank,
    }


def _serialize_stream(s: _Stream) -> dict:
    return {
        "id": s.id,
        "label": s.label,
        "bank": s.bank,
        "cadence": s.cadence,
        "cadence_label": s.cadence_label,
        "period_days": s.period_days,
        "tolerance_days": s.tolerance_days,
        "occurrence_count": len(s.occurrences),
        "first_date": s.first_date.isoformat(),
        "last_date": s.last_date.isoformat(),
        "expected_next": s.expected_next.isoformat(),
        "status": s.status,
        "overdue_days": s.overdue_days,
        "latest_amount": str(s.latest_amount.quantize(TWO_PLACES)),
        "previous_amount": str(s.previous_amount.quantize(TWO_PLACES)),
        "delta": str(s.delta.quantize(TWO_PLACES)),
        "delta_pct": str(s.delta_pct) if s.delta_pct is not None else None,
        "median_amount": str(s.median_amount),  # already quantized to 2dp at construction
        "total_amount": str(s.total_amount.quantize(TWO_PLACES)),
        "occurrences": [_serialize_occurrence(r) for r in s.occurrences],
    }


def build_income_report(
    rows: list[IncomeRow],
    today: date,
    base_currency: str,
    unconverted_count: int,
) -> dict:
    """Steps 1-6: cluster `rows` into recurring streams + one-offs and
    assemble the full Income page payload (see the plan's documented
    response contract). Does not include `generated_on` -- the router adds
    that from the same `today` it passed in here."""
    rows_sorted = sorted(rows, key=lambda r: (r.date, r.id))

    # --- Step 1: bucket by (bank, normalized merchant); empty keys are
    # never groupable and go straight to the one-off pool (J-01). ---
    buckets: dict[tuple[str, str], list[IncomeRow]] = {}
    one_off_rows: list[IncomeRow] = []
    for row in rows_sorted:
        key = normalize_merchant(row.description)
        if not key:
            one_off_rows.append(row)
            continue
        buckets.setdefault((row.bank, key), []).append(row)

    # --- Steps 2-5: cluster each bucket, infer cadence, gate regularity,
    # predict + score recognized streams. ---
    streams: list[_Stream] = []
    for (bank, merchant_key), bucket_rows in buckets.items():
        clusters = _cluster_by_amount(bucket_rows)
        for cluster_index, cluster in enumerate(clusters):
            if len(cluster) < MIN_OCCURRENCES:
                one_off_rows.extend(cluster)
                continue

            dates = [r.date for r in cluster]
            gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
            median_gap = statistics.median(gaps)

            cadence_info = _infer_cadence(median_gap)
            if cadence_info is None:
                one_off_rows.extend(cluster)
                continue
            cadence, cadence_label, period_days = cadence_info

            if not _is_regular(gaps, period_days):
                one_off_rows.extend(cluster)
                continue

            tolerance_days = _tolerance_days(period_days)
            first_date = dates[0]
            last_date = dates[-1]
            expected_next = _expected_next(last_date, cadence, period_days)
            overdue_days = (today - expected_next).days
            status = _status_for(overdue_days, tolerance_days, period_days)

            latest_amount = cluster[-1].amount
            previous_amount = cluster[-2].amount
            delta = latest_amount - previous_amount
            delta_pct: Decimal | None = None
            if previous_amount != 0:
                delta_pct = (delta / abs(previous_amount) * 100).quantize(ONE_PLACE)

            amounts = [r.amount for r in cluster]
            median_amount = statistics.median(amounts)
            if not isinstance(median_amount, Decimal):  # pragma: no cover - defensive
                median_amount = Decimal(str(median_amount))
            median_amount = median_amount.quantize(TWO_PLACES)
            total_amount = sum(amounts, Decimal("0"))

            stream_id = hashlib.sha1(
                f"{bank}|{merchant_key}|{cluster_index}".encode()
            ).hexdigest()[:12]

            streams.append(
                _Stream(
                    id=stream_id,
                    label=cluster[-1].description[:60],
                    bank=bank,
                    cadence=cadence,
                    cadence_label=cadence_label,
                    period_days=period_days,
                    tolerance_days=tolerance_days,
                    first_date=first_date,
                    last_date=last_date,
                    expected_next=expected_next,
                    status=status,
                    overdue_days=overdue_days,
                    latest_amount=latest_amount,
                    previous_amount=previous_amount,
                    delta=delta,
                    delta_pct=delta_pct,
                    median_amount=median_amount,
                    total_amount=total_amount,
                    occurrences=cluster,
                )
            )

    # --- Step 6: assemble, needing-attention streams first, then by
    # median amount descending; one-offs most-recent-first. ---
    streams.sort(key=lambda s: (0 if s.status in _PRIORITY_STATUSES else 1, -s.median_amount))
    one_off_rows.sort(key=lambda r: (r.date, r.id), reverse=True)

    stream_row_ids = {row.id for s in streams for row in s.occurrences}

    # --- Totals ---
    def _sum_amounts(predicate) -> Decimal:
        return sum((r.amount for r in rows_sorted if predicate(r)), Decimal("0"))

    this_month_total = _sum_amounts(lambda r: r.date.year == today.year and r.date.month == today.month)
    last_month_year, last_month_num = _prev_month(today)
    last_month_total = _sum_amounts(lambda r: r.date.year == last_month_year and r.date.month == last_month_num)
    ytd_total = _sum_amounts(lambda r: r.date.year == today.year)

    month_delta = this_month_total - last_month_total
    month_delta_pct: Decimal | None = None
    if last_month_total != 0:
        month_delta_pct = (month_delta / abs(last_month_total) * 100).quantize(ONE_PLACE)

    recurring_monthly_estimate = sum(
        (s.median_amount * (MONTH_DAYS_AVG / s.period_days) for s in streams if s.status != "ended"),
        Decimal("0"),
    ).quantize(TWO_PLACES)

    # --- Monthly: contiguous 12-calendar-month window ending in today's
    # month, zero-filled so income gaps are visible rather than skipped. ---
    today_first = date(today.year, today.month, 1)
    month_keys = [_month_key(_add_months(today_first, -i)) for i in range(11, -1, -1)]
    monthly_recurring = {mk: Decimal("0") for mk in month_keys}
    monthly_one_off = {mk: Decimal("0") for mk in month_keys}
    for row in rows_sorted:
        mk = _month_key(row.date)
        if mk not in monthly_recurring:
            continue
        if row.id in stream_row_ids:
            monthly_recurring[mk] += row.amount
        else:
            monthly_one_off[mk] += row.amount

    monthly = [
        {
            "month": mk,
            "recurring": str(monthly_recurring[mk].quantize(TWO_PLACES)),
            "one_off": str(monthly_one_off[mk].quantize(TWO_PLACES)),
            "total": str((monthly_recurring[mk] + monthly_one_off[mk]).quantize(TWO_PLACES)),
        }
        for mk in month_keys
    ]

    return {
        "base_currency": base_currency,
        "unconverted_count": unconverted_count,
        "totals": {
            "this_month": str(this_month_total.quantize(TWO_PLACES)),
            "last_month": str(last_month_total.quantize(TWO_PLACES)),
            "month_delta": str(month_delta.quantize(TWO_PLACES)),
            "month_delta_pct": str(month_delta_pct) if month_delta_pct is not None else None,
            "ytd": str(ytd_total.quantize(TWO_PLACES)),
            "recurring_monthly_estimate": str(recurring_monthly_estimate),
            "transaction_count": len(rows_sorted),
            "stream_count": len(streams),
            "one_off_count": len(one_off_rows),
        },
        "streams": [_serialize_stream(s) for s in streams],
        "one_offs": [_serialize_occurrence(r) for r in one_off_rows],
        "monthly": monthly,
    }

"""Unit tests for app.services.income -- plain synchronous pytest functions
over constructed IncomeRow lists with a hardcoded `today`. No client fixture,
no DB, no network: this pins the pure recurring-detection algorithm exactly
(see the plan's Steps 1-6 and judgment calls J-01..J-12)."""

from datetime import date, timedelta
from decimal import Decimal

from app.services.income import (
    IncomeRow,
    _status_for,
    build_income_report,
)


def _row(id: int, d: date, amount: str, description: str = "ACME CORP SALARY", bank: str = "Revolut") -> IncomeRow:
    dec = Decimal(amount)
    return IncomeRow(
        id=id,
        date=d,
        description=description,
        bank=bank,
        amount=dec,
        original_amount=dec,
        original_currency="ILS",
    )


def _monthly_dates(start: date, count: int, step_days: int = 30) -> list[date]:
    return [start + timedelta(days=step_days * i) for i in range(count)]


# --------------------------------------------------------------------------
# Cadence recognition
# --------------------------------------------------------------------------


def test_six_monthly_salary_rows_form_one_recognized_stream():
    dates = _monthly_dates(date(2026, 1, 1), 6)
    rows = [_row(i, d, "10000.00") for i, d in enumerate(dates)]

    report = build_income_report(rows, today=date(2026, 7, 1), base_currency="ILS", unconverted_count=0)

    assert len(report["streams"]) == 1
    stream = report["streams"][0]
    assert stream["cadence"] == "monthly"
    assert stream["period_days"] == 30
    assert stream["occurrence_count"] == 6
    from app.services.income import _add_months

    assert stream["expected_next"] == _add_months(dates[-1], 1).isoformat()
    assert report["one_offs"] == []


def test_biweekly_gaps_are_recognized():
    start = date(2026, 1, 1)
    gaps = [14, 14, 15, 13]
    dates = [start]
    for g in gaps:
        dates.append(dates[-1] + timedelta(days=g))
    rows = [_row(i, d, "1000.00") for i, d in enumerate(dates)]

    report = build_income_report(rows, today=date(2026, 3, 1), base_currency="ILS", unconverted_count=0)

    assert len(report["streams"]) == 1
    assert report["streams"][0]["cadence"] == "biweekly"
    assert report["streams"][0]["period_days"] == 14


def test_two_occurrences_are_not_a_stream():
    dates = _monthly_dates(date(2026, 1, 1), 2)
    rows = [_row(i, d, "1000.00") for i, d in enumerate(dates)]

    report = build_income_report(rows, today=date(2026, 3, 1), base_currency="ILS", unconverted_count=0)

    assert report["streams"] == []
    assert len(report["one_offs"]) == 2


def test_irregular_gaps_are_not_recognized():
    start = date(2026, 1, 1)
    gaps = [5, 40, 3]
    dates = [start]
    for g in gaps:
        dates.append(dates[-1] + timedelta(days=g))
    rows = [_row(i, d, "1000.00") for i, d in enumerate(dates)]

    report = build_income_report(rows, today=date(2026, 3, 1), base_currency="ILS", unconverted_count=0)

    assert report["streams"] == []
    assert len(report["one_offs"]) == 4


def test_one_wildly_off_monthly_gap_fails_regularity_gate():
    # 4 occurrences, gaps of 30, 30, 75 -> 2/3 conforming = 0.67 < 0.75 (J-05).
    start = date(2026, 1, 1)
    gaps = [30, 30, 75]
    dates = [start]
    for g in gaps:
        dates.append(dates[-1] + timedelta(days=g))
    rows = [_row(i, d, "1000.00") for i, d in enumerate(dates)]

    report = build_income_report(rows, today=date(2026, 6, 1), base_currency="ILS", unconverted_count=0)

    assert report["streams"] == []
    assert len(report["one_offs"]) == 4


# --------------------------------------------------------------------------
# Amount cohesion / grouping key
# --------------------------------------------------------------------------


def test_amount_cohesion_never_lets_small_amounts_pollute_a_salary_stream():
    salary_dates = _monthly_dates(date(2026, 1, 1), 3)
    small_dates = _monthly_dates(date(2026, 4, 1), 3)
    rows = [_row(i, d, "1000.00") for i, d in enumerate(salary_dates)]
    rows += [_row(i + 100, d, "30.00") for i, d in enumerate(small_dates)]

    report = build_income_report(rows, today=date(2026, 6, 1), base_currency="ILS", unconverted_count=0)

    assert len(report["streams"]) == 2
    amounts = sorted(s["median_amount"] for s in report["streams"])
    assert amounts == ["1000.00", "30.00"]


def test_same_description_different_bank_are_separate_streams():
    dates = _monthly_dates(date(2026, 1, 1), 3)
    rows = [_row(i, d, "1000.00", bank="Revolut") for i, d in enumerate(dates)]
    rows += [_row(i + 100, d, "1000.00", bank="CA") for i, d in enumerate(dates)]

    report = build_income_report(rows, today=date(2026, 4, 1), base_currency="ILS", unconverted_count=0)

    assert len(report["streams"]) == 2
    banks = {s["bank"] for s in report["streams"]}
    assert banks == {"Revolut", "CA"}


def test_empty_normalized_key_is_never_grouped():
    dates = _monthly_dates(date(2026, 1, 1), 3)
    rows = [_row(i, d, "1000.00", description="123 456") for i, d in enumerate(dates)]

    report = build_income_report(rows, today=date(2026, 4, 1), base_currency="ILS", unconverted_count=0)

    assert report["streams"] == []
    assert len(report["one_offs"]) == 3


# --------------------------------------------------------------------------
# Status ladder (J-06)
# --------------------------------------------------------------------------


def test_status_for_boundaries():
    period_days = 30
    tolerance_days = 8  # max(ceil(0.25 * 30), 3)

    assert _status_for(-9, tolerance_days, period_days) == "upcoming"
    assert _status_for(-8, tolerance_days, period_days) == "due"
    assert _status_for(0, tolerance_days, period_days) == "due"
    assert _status_for(8, tolerance_days, period_days) == "due"
    assert _status_for(9, tolerance_days, period_days) == "late"
    assert _status_for(30, tolerance_days, period_days) == "late"
    assert _status_for(31, tolerance_days, period_days) == "missing"
    assert _status_for(60, tolerance_days, period_days) == "missing"
    assert _status_for(61, tolerance_days, period_days) == "ended"


def test_status_ladder_end_to_end_via_build_income_report():
    # Calendar-month dates (not the fixed 30-day helper) so the math is
    # exact: gaps [31, 28] -> median 29.5 -> monthly, period_days=30,
    # tolerance_days=8, last_date=2026-03-01, expected_next=2026-04-01.
    dates = [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]
    rows = [_row(i, d, "1000.00") for i, d in enumerate(dates)]

    upcoming = build_income_report(rows, today=date(2026, 3, 20), base_currency="ILS", unconverted_count=0)
    assert upcoming["streams"][0]["status"] == "upcoming"

    due = build_income_report(rows, today=date(2026, 4, 1), base_currency="ILS", unconverted_count=0)
    assert due["streams"][0]["status"] == "due"

    late = build_income_report(rows, today=date(2026, 4, 15), base_currency="ILS", unconverted_count=0)
    assert late["streams"][0]["status"] == "late"

    missing = build_income_report(rows, today=date(2026, 5, 5), base_currency="ILS", unconverted_count=0)
    assert missing["streams"][0]["status"] == "missing"

    ended = build_income_report(rows, today=date(2026, 7, 1), base_currency="ILS", unconverted_count=0)
    assert ended["streams"][0]["status"] == "ended"


# --------------------------------------------------------------------------
# Delta / delta_pct
# --------------------------------------------------------------------------


def test_delta_and_delta_pct_are_exact_decimal_strings():
    dates = _monthly_dates(date(2026, 1, 1), 3)
    amounts = ["10000.00", "10500.00", "11000.00"]
    rows = [_row(i, d, a) for i, (d, a) in enumerate(zip(dates, amounts))]

    report = build_income_report(rows, today=date(2026, 3, 1), base_currency="ILS", unconverted_count=0)

    stream = report["streams"][0]
    assert stream["latest_amount"] == "11000.00"
    assert stream["previous_amount"] == "10500.00"
    assert stream["delta"] == "500.00"
    assert stream["delta_pct"] == "4.8"


def test_delta_pct_is_none_when_previous_amount_is_zero():
    dates = _monthly_dates(date(2026, 1, 1), 3)
    amounts = ["0.00", "0.00", "50.00"]
    rows = [_row(i, d, a, description="Weird zero stream") for i, (d, a) in enumerate(zip(dates, amounts))]
    # amount cohesion: median of [0, 0] is 0, tolerance floor 50 -> 50.00
    # still joins the cluster (abs(50-0) == 50 <= 50).

    report = build_income_report(rows, today=date(2026, 3, 1), base_currency="ILS", unconverted_count=0)

    assert len(report["streams"]) == 1
    stream = report["streams"][0]
    assert stream["delta_pct"] is None
    # the zero amount itself must still serialize as "0.00", not be dropped
    # by Decimal("0.00")'s falsiness (the known bug in transactions.py).
    assert stream["occurrences"][0]["amount"] == "0.00"


# --------------------------------------------------------------------------
# Monthly series
# --------------------------------------------------------------------------


def test_monthly_series_is_contiguous_ascending_and_zero_filled():
    report = build_income_report([], today=date(2026, 7, 15), base_currency="ILS", unconverted_count=0)

    monthly = report["monthly"]
    assert len(monthly) == 12
    months = [m["month"] for m in monthly]
    assert months == sorted(months)
    assert months[-1] == "2026-07"
    assert months[0] == "2025-08"
    assert all(m["recurring"] == "0.00" and m["one_off"] == "0.00" and m["total"] == "0.00" for m in monthly)


# --------------------------------------------------------------------------
# recurring_monthly_estimate
# --------------------------------------------------------------------------


def test_recurring_monthly_estimate_normalizes_biweekly_upward_and_excludes_ended():
    # Biweekly stream, median 1000 -> normalized monthly should exceed 2000.
    start = date(2026, 1, 1)
    dates = [start + timedelta(days=14 * i) for i in range(4)]
    biweekly_rows = [_row(i, d, "1000.00", description="Freelance Client A") for i, d in enumerate(dates)]

    # A separate, ended monthly stream (last paid long before `today`).
    ended_dates = _monthly_dates(date(2020, 1, 1), 3)
    ended_rows = [_row(i + 100, d, "5000.00", description="Old Employer") for i, d in enumerate(ended_dates)]

    report = build_income_report(
        biweekly_rows + ended_rows, today=date(2026, 3, 1), base_currency="ILS", unconverted_count=0
    )

    statuses = {s["label"]: s["status"] for s in report["streams"]}
    assert statuses["Old Employer"] == "ended"
    assert Decimal(report["totals"]["recurring_monthly_estimate"]) > Decimal("2000")


# --------------------------------------------------------------------------
# Empty input
# --------------------------------------------------------------------------


def test_empty_input_produces_zeroed_report():
    report = build_income_report([], today=date(2026, 7, 15), base_currency="ILS", unconverted_count=0)

    assert report["streams"] == []
    assert report["one_offs"] == []
    totals = report["totals"]
    assert totals["this_month"] == "0.00"
    assert totals["last_month"] == "0.00"
    assert totals["ytd"] == "0.00"
    assert totals["transaction_count"] == 0
    assert totals["stream_count"] == 0
    assert totals["one_off_count"] == 0
    assert len(report["monthly"]) == 12

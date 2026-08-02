from datetime import datetime
from decimal import Decimal

from app.services.recurring import TxnRow, detect_recurring_large_expenses


def _row(id_, month, day, amount, description="Landlord Rent Co", year=2026):
    return TxnRow(
        id=id_,
        description=description,
        date=datetime(year, month, day),
        amount=Decimal(amount),
        category_name="Rent",
        group_name="Housing",
    )


def test_stable_recurring_expense_detected():
    rows = [
        _row(1, 1, 1, "1000.00"),
        _row(2, 2, 1, "1000.00"),
        _row(3, 3, 1, "1000.00"),
    ]

    groups = detect_recurring_large_expenses(rows, threshold=Decimal("100"), as_of=datetime(2026, 3, 10))

    assert len(groups) == 1
    g = groups[0]
    assert g.status == "stable"
    assert g.overdue is False
    assert g.latest_amount == Decimal("1000.00")
    assert g.transaction_ids == [1, 2, 3]


def test_amount_increase_flagged():
    rows = [
        _row(1, 1, 1, "1000.00"),
        _row(2, 2, 1, "1000.00"),
        _row(3, 3, 1, "1300.00"),  # +30%
    ]

    groups = detect_recurring_large_expenses(rows, threshold=Decimal("100"))

    assert groups[0].status == "increased"
    assert groups[0].pct_change > 0


def test_amount_decrease_flagged():
    rows = [
        _row(1, 1, 1, "1000.00"),
        _row(2, 2, 1, "1000.00"),
        _row(3, 3, 1, "600.00"),  # -40%
    ]

    groups = detect_recurring_large_expenses(rows, threshold=Decimal("100"))

    assert groups[0].status == "decreased"
    assert groups[0].pct_change < 0


def test_small_fluctuation_within_tolerance_is_stable():
    rows = [
        _row(1, 1, 1, "1000.00"),
        _row(2, 2, 1, "1000.00"),
        _row(3, 3, 1, "1050.00"),  # +5%, under the 15% tolerance
    ]

    groups = detect_recurring_large_expenses(rows, threshold=Decimal("100"))

    assert groups[0].status == "stable"


def test_below_threshold_not_detected():
    rows = [
        _row(1, 1, 1, "10.00"),
        _row(2, 2, 1, "10.00"),
        _row(3, 3, 1, "10.00"),
    ]

    groups = detect_recurring_large_expenses(rows, threshold=Decimal("100"))

    assert groups == []


def test_fewer_than_three_months_not_recurring():
    rows = [
        _row(1, 1, 1, "1000.00"),
        _row(2, 2, 1, "1000.00"),
    ]

    groups = detect_recurring_large_expenses(rows, threshold=Decimal("100"))

    assert groups == []


def test_overdue_when_gap_exceeds_cadence():
    rows = [
        _row(1, 1, 1, "1000.00"),
        _row(2, 2, 1, "1000.00"),
        _row(3, 3, 1, "1000.00"),
    ]
    # ~30 day cadence historically; "as_of" is 90 days after the last charge.
    as_of = datetime(2026, 6, 1)

    groups = detect_recurring_large_expenses(rows, threshold=Decimal("100"), as_of=as_of)

    assert groups[0].overdue is True


def test_not_overdue_within_cadence():
    rows = [
        _row(1, 1, 1, "1000.00"),
        _row(2, 2, 1, "1000.00"),
        _row(3, 3, 1, "1000.00"),
    ]
    as_of = datetime(2026, 3, 10)  # 9 days after the last charge

    groups = detect_recurring_large_expenses(rows, threshold=Decimal("100"), as_of=as_of)

    assert groups[0].overdue is False


def test_different_merchants_grouped_separately():
    rows = [
        _row(1, 1, 1, "1000.00", description="Landlord Rent Co"),
        _row(2, 2, 1, "1000.00", description="Landlord Rent Co"),
        _row(3, 3, 1, "1000.00", description="Landlord Rent Co"),
        _row(4, 1, 15, "150.00", description="Gym Membership Plus"),
        _row(5, 2, 15, "150.00", description="Gym Membership Plus"),
        _row(6, 3, 15, "150.00", description="Gym Membership Plus"),
    ]

    groups = detect_recurring_large_expenses(rows, threshold=Decimal("100"))

    assert len(groups) == 2
    # Largest latest amount first.
    assert groups[0].latest_amount > groups[1].latest_amount


def test_multiple_charges_same_month_are_summed():
    rows = [
        _row(1, 1, 1, "500.00", description="Amazon"),
        _row(2, 1, 15, "500.00", description="Amazon"),
        _row(3, 2, 1, "1000.00", description="Amazon"),
        _row(4, 3, 1, "1000.00", description="Amazon"),
    ]

    groups = detect_recurring_large_expenses(rows, threshold=Decimal("100"))

    assert len(groups) == 1
    assert groups[0].occurrences[0]["amount"] == "1000.00"

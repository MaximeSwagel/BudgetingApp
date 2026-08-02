from datetime import datetime
from decimal import Decimal

from app.services.transfers import (
    LOW_TOLERANCE_PCT,
    TransferLeg,
    match_transfers,
)


def _leg(
    id_,
    *,
    day,
    amount,
    currency="ILS",
    converted=None,
    bank="Revolut",
    description="Transfer",
    month=1,
    year=2026,
):
    amount = Decimal(amount)
    converted = Decimal(converted) if converted is not None else amount
    return TransferLeg(
        id=id_,
        date=datetime(year, month, day),
        description=description,
        original_amount=amount,
        original_currency=currency,
        converted_amount=converted,
        bank=bank,
    )


def test_same_currency_exact_opposite_same_day_is_high_confidence():
    legs = [
        _leg(1, day=1, amount="-500.00", currency="EUR", bank="Revolut"),
        _leg(2, day=1, amount="500.00", currency="ILS", bank="CA"),
    ]
    pairs = match_transfers(legs)
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.outgoing_id == 1
    assert pair.incoming_id == 2
    assert pair.confidence == "high"
    # Self-check: the two legs net to ~zero in base currency.
    out_leg = next(l for l in legs if l.id == pair.outgoing_id)
    in_leg = next(l for l in legs if l.id == pair.incoming_id)
    assert out_leg.converted_amount + in_leg.converted_amount == Decimal("0.00")


def test_cross_currency_within_half_percent_one_day_is_high():
    legs = [
        _leg(1, day=1, amount="-1000.00", currency="EUR", converted="-1000.00", bank="Revolut"),
        _leg(2, day=2, amount="4000.00", currency="ILS", converted="996.00", bank="CA"),
    ]
    pairs = match_transfers(legs)
    assert len(pairs) == 1
    assert pairs[0].confidence == "high"


def test_cross_currency_within_two_percent_three_days_is_medium():
    legs = [
        _leg(1, day=1, amount="-1000.00", currency="EUR", converted="-1000.00", bank="Revolut"),
        _leg(4, day=4, amount="985.00", currency="ILS", converted="985.00", bank="CA"),
    ]
    pairs = match_transfers(legs)
    assert len(pairs) == 1
    assert pairs[0].confidence == "medium"


def test_cross_currency_within_five_percent_five_days_is_low():
    legs = [
        _leg(1, day=1, amount="-1000.00", currency="EUR", converted="-1000.00", bank="Revolut"),
        _leg(6, day=6, amount="955.00", currency="ILS", converted="955.00", bank="CA"),
    ]
    pairs = match_transfers(legs, window_days=5, tolerance_pct=LOW_TOLERANCE_PCT)
    assert len(pairs) == 1
    assert pairs[0].confidence == "low"


def test_same_account_key_never_pairs_even_with_opposite_amounts():
    legs = [
        _leg(1, day=1, amount="-500.00", currency="ILS", bank="Revolut"),
        _leg(2, day=1, amount="500.00", currency="ILS", bank="Revolut"),
    ]
    pairs = match_transfers(legs)
    assert pairs == []


def test_two_outflows_never_pair():
    legs = [
        _leg(1, day=1, amount="-500.00", currency="ILS", bank="Revolut"),
        _leg(2, day=1, amount="-500.00", currency="ILS", bank="CA"),
    ]
    assert match_transfers(legs) == []


def test_two_inflows_never_pair():
    legs = [
        _leg(1, day=1, amount="500.00", currency="ILS", bank="Revolut"),
        _leg(2, day=1, amount="500.00", currency="ILS", bank="CA"),
    ]
    assert match_transfers(legs) == []


def test_inbound_one_day_early_is_still_a_candidate():
    legs = [
        _leg(1, day=5, amount="-500.00", currency="ILS", bank="Revolut"),
        _leg(2, day=4, amount="500.00", currency="ILS", bank="CA"),
    ]
    pairs = match_transfers(legs)
    assert len(pairs) == 1
    assert pairs[0].day_gap == -1


def test_inbound_two_days_early_is_not_a_candidate():
    legs = [
        _leg(1, day=5, amount="-500.00", currency="ILS", bank="Revolut"),
        _leg(2, day=3, amount="500.00", currency="ILS", bank="CA"),
    ]
    assert match_transfers(legs) == []


def test_amount_beyond_low_tolerance_produces_no_pair():
    legs = [
        _leg(1, day=1, amount="-1000.00", currency="EUR", converted="-1000.00", bank="Revolut"),
        _leg(2, day=1, amount="900.00", currency="ILS", converted="900.00", bank="CA"),
    ]
    assert match_transfers(legs) == []


def test_date_beyond_window_produces_no_pair():
    legs = [
        _leg(1, day=1, amount="-500.00", currency="ILS", bank="Revolut"),
        _leg(2, day=10, amount="500.00", currency="ILS", bank="CA"),
    ]
    assert match_transfers(legs) == []


def test_one_to_one_consumption_picks_better_scoring_inflow_deterministically():
    legs = [
        _leg(1, day=1, amount="-1000.00", currency="ILS", bank="Revolut"),
        _leg(2, day=1, amount="1000.00", currency="ILS", bank="CA", description="Exact match"),
        _leg(3, day=1, amount="990.00", currency="ILS", bank="Leumi", description="Looser match"),
    ]
    pairs = match_transfers(legs)
    assert len(pairs) == 1
    assert pairs[0].incoming_id == 2

    # Deterministic across runs.
    pairs_again = match_transfers(legs)
    assert pairs_again == pairs


def test_already_matched_ids_are_never_reused():
    legs = [
        _leg(1, day=1, amount="-500.00", currency="ILS", bank="Revolut"),
        _leg(2, day=1, amount="500.00", currency="ILS", bank="CA"),
    ]
    pairs = match_transfers(legs, already_matched_ids={1})
    assert pairs == []

    pairs = match_transfers(legs, already_matched_ids={2})
    assert pairs == []


def test_rejected_pair_is_never_recreated():
    legs = [
        _leg(1, day=1, amount="-500.00", currency="ILS", bank="Revolut"),
        _leg(2, day=1, amount="500.00", currency="ILS", bank="CA"),
    ]
    pairs = match_transfers(legs, rejected_pairs={(1, 2)})
    assert pairs == []


def test_fee_amount_is_shortfall_between_legs():
    legs = [
        _leg(1, day=1, amount="-1000.00", currency="ILS", bank="Revolut"),
        _leg(2, day=1, amount="990.00", currency="ILS", bank="CA"),
    ]
    pairs = match_transfers(legs)
    assert len(pairs) == 1
    assert pairs[0].fee_amount == Decimal("10.00")


def test_zero_fee_is_reported_as_zero_not_none():
    legs = [
        _leg(1, day=1, amount="-500.00", currency="ILS", bank="Revolut"),
        _leg(2, day=1, amount="500.00", currency="ILS", bank="CA"),
    ]
    pairs = match_transfers(legs)
    assert len(pairs) == 1
    assert pairs[0].fee_amount == Decimal("0.00")
    assert pairs[0].fee_amount is not None


def test_incoming_leg_receiving_more_than_sent_has_no_fee():
    legs = [
        _leg(1, day=1, amount="-500.00", currency="ILS", bank="Revolut"),
        _leg(2, day=1, amount="505.00", currency="ILS", bank="CA"),
    ]
    pairs = match_transfers(legs)
    assert len(pairs) == 1
    assert pairs[0].fee_amount is None


def test_leg_with_none_converted_amount_is_never_matched():
    unconverted = TransferLeg(
        id=1,
        date=datetime(2026, 1, 1),
        description="Unconverted",
        original_amount=Decimal("-500.00"),
        original_currency="ILS",
        converted_amount=None,
        bank="Revolut",
    )
    legs = [
        unconverted,
        _leg(2, day=1, amount="500.00", currency="ILS", bank="CA"),
    ]
    assert match_transfers(legs) == []

"""Internal-transfer detection: pairs up two transactions that are the two
legs of the same movement between the user's own bank accounts.

Purely computed from constructed inputs -- no DB session, no network call,
no wall-clock read inside the matching logic itself -- mirroring the shape
of `app.services.recurring`. The caller (an async orchestrator elsewhere)
is responsible for fetching candidate legs, persisting results, and
supplying `already_matched_ids` / `rejected_pairs`.

Known limitation (D-04): there is no `Account` entity in this codebase. An
"account" is derived here as `f"{bank}:{original_currency}"`. Two accounts
at the same bank in the same currency are therefore indistinguishable, and
a transfer between them can never be detected -- a pair REQUIRES the two
legs' account keys to differ.

Tiering policy (D-05): silently hiding money in a budgeting app is the
failure mode to avoid, so only `high`-confidence pairs are meant to be
auto-excluded by the caller (this module does not decide `status` --  it
only grades `confidence`). `medium`/`low` pairs should stay fully visible
until a human confirms them.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

WINDOW_DAYS = 3
HIGH_TOLERANCE_PCT = Decimal("0.005")
MEDIUM_TOLERANCE_PCT = Decimal("0.02")
LOW_TOLERANCE_PCT = Decimal("0.05")
HIGH_WINDOW_DAYS = 1
MEDIUM_WINDOW_DAYS = 3
# The inbound leg may post up to this many days BEFORE the outbound leg --
# real Revolut internal moves can land out of order within the same batch
# (D-12), so the window is `-EARLY_ARRIVAL_DAYS..window_days`, not `0..N`.
EARLY_ARRIVAL_DAYS = 1


@dataclass
class TransferLeg:
    id: int
    date: datetime
    description: str
    original_amount: Decimal  # signed
    original_currency: str
    converted_amount: Decimal | None  # signed, base currency
    bank: str


@dataclass
class TransferPair:
    outgoing_id: int
    incoming_id: int
    confidence: str  # high | medium | low
    fee_amount: Decimal | None
    day_gap: int
    rel_delta: Decimal


def account_key(leg: TransferLeg) -> str:
    return f"{leg.bank}:{leg.original_currency}"


def _rel_delta(conv_out: Decimal, conv_in: Decimal) -> Decimal:
    abs_out = abs(conv_out)
    abs_in = abs(conv_in)
    denom = max(abs_out, abs_in)
    if denom == 0:
        return Decimal("0")
    return abs(abs_out - abs_in) / denom


def _fee_amount(conv_out: Decimal, conv_in: Decimal) -> Decimal | None:
    """The shortfall between what left and what arrived, or None when the
    incoming leg received AT LEAST as much as left (not a fee)."""
    diff = abs(conv_out) - abs(conv_in)
    return diff if diff >= 0 else None


_CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}


def _grade(
    day_gap: int,
    rel_delta: Decimal,
    same_currency_exact_match: bool,
) -> str:
    if abs(day_gap) <= HIGH_WINDOW_DAYS and (same_currency_exact_match or rel_delta <= HIGH_TOLERANCE_PCT):
        return "high"
    if day_gap <= MEDIUM_WINDOW_DAYS and rel_delta <= MEDIUM_TOLERANCE_PCT:
        return "medium"
    return "low"


def match_transfers(
    legs: list[TransferLeg],
    *,
    window_days: int = WINDOW_DAYS,
    tolerance_pct: Decimal = LOW_TOLERANCE_PCT,
    already_matched_ids: set[int] | None = None,
    rejected_pairs: set[tuple[int, int]] | None = None,
) -> list[TransferPair]:
    already_matched_ids = already_matched_ids or set()
    rejected_pairs = rejected_pairs or set()

    outflows: list[TransferLeg] = []
    inflows: list[TransferLeg] = []
    for leg in legs:
        if leg.id in already_matched_ids:
            continue
        if leg.converted_amount is None:
            continue
        if leg.converted_amount < 0:
            outflows.append(leg)
        elif leg.converted_amount > 0:
            inflows.append(leg)

    candidates: list[tuple[str, Decimal, int, TransferLeg, TransferLeg, Decimal | None]] = []

    for outgoing in outflows:
        for incoming in inflows:
            if account_key(outgoing) == account_key(incoming):
                continue
            if (outgoing.id, incoming.id) in rejected_pairs or (incoming.id, outgoing.id) in rejected_pairs:
                continue

            day_gap = (incoming.date.date() - outgoing.date.date()).days
            if not (-EARLY_ARRIVAL_DAYS <= day_gap <= window_days):
                continue

            conv_out = outgoing.converted_amount
            conv_in = incoming.converted_amount
            rel_delta = _rel_delta(conv_out, conv_in)
            if rel_delta > tolerance_pct:
                continue

            same_currency_exact_match = (
                outgoing.original_currency == incoming.original_currency
                and abs(outgoing.original_amount) == abs(incoming.original_amount)
            )
            confidence = _grade(day_gap, rel_delta, same_currency_exact_match)
            fee_amount = _fee_amount(conv_out, conv_in)

            candidates.append((confidence, rel_delta, day_gap, outgoing, incoming, fee_amount))

    # Deterministic, greedy one-to-one consumption: best confidence first,
    # then tightest amount match, then tightest date match, then a stable
    # id-based tiebreak so repeated runs over identical input always
    # produce the identical result.
    candidates.sort(
        key=lambda c: (
            _CONFIDENCE_RANK[c[0]],
            c[1],
            abs(c[2]),
            c[3].id,
            c[4].id,
        )
    )

    consumed: set[int] = set()
    pairs: list[TransferPair] = []
    for confidence, rel_delta, day_gap, outgoing, incoming, fee_amount in candidates:
        if outgoing.id in consumed or incoming.id in consumed:
            continue
        consumed.add(outgoing.id)
        consumed.add(incoming.id)
        pairs.append(
            TransferPair(
                outgoing_id=outgoing.id,
                incoming_id=incoming.id,
                confidence=confidence,
                fee_amount=fee_amount,
                day_gap=day_gap,
                rel_delta=rel_delta,
            )
        )

    return pairs

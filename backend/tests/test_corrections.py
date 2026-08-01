import io

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import Transaction
from app.services.corrections import match_key, normalize_merchant


def test_normalize_merchant_ignores_case_punctuation_and_digits():
    a = normalize_merchant("SUPER-YUDA  TLV 12/03/26")
    b = normalize_merchant("super yuda tlv")
    assert a == b
    assert a != ""


def test_normalize_merchant_preserves_non_ascii_letters():
    # Bank Leumi is an Israeli bank; an ASCII-only filter would collapse
    # every Hebrew merchant onto the same empty key.
    hebrew_key = normalize_merchant("סופר יודה")
    accented_key = normalize_merchant("Café Rüdesheimer")
    assert hebrew_key != ""
    assert accented_key != ""


def test_normalize_merchant_returns_empty_when_nothing_identifying_remains():
    assert normalize_merchant("  12/03  ") == ""


def test_match_key_containment():
    assert match_key("SUPER YUDA TEL AVIV", {"super yuda": object()}) == "super yuda"


def test_match_key_rejects_short_candidate_by_containment():
    # "xyz" (3 chars) is below MIN_KEY_LEN and must never match by
    # containment, even though it appears inside the normalized description.
    assert match_key("XYZ CORP LTD", {"xyz": object()}) is None


def test_match_key_prefers_longer_candidate_when_multiple_match():
    keys = {"super": object(), "super yuda": object()}
    assert match_key("super yuda tel aviv", keys) == "super yuda"


# ---------------------------------------------------------------------------
# API tests (Task 2): /api/corrections, correction_status on the list
# response, and correction-aware categorization at both call sites.
# ---------------------------------------------------------------------------

CORRECTIONS_CSV = (
    "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
    "CARD_PAYMENT,Current,2026-01-05 10:00:00,2026-01-05 10:00:01,Super Yuda,-20.00,0,ILS,COMPLETED,150.00\n"
    "CARD_PAYMENT,Current,2026-01-06 11:00:00,2026-01-06 11:00:01,Super Yuda,-15.00,0,ILS,COMPLETED,135.00\n"
    "CARD_PAYMENT,Current,2026-01-07 12:00:00,2026-01-07 12:00:01,Weird Merchant,-8.50,0,ILS,COMPLETED,126.50\n"
)


async def _upload_corrections_csv(client):
    resp = await client.post(
        "/api/upload", files={"file": ("a.csv", io.BytesIO(CORRECTIONS_CSV.encode()), "text/csv")}
    )
    return resp.json()


async def _category_id(client, group_name, category_name):
    categories = (await client.get("/api/categories")).json()
    return next(
        c["id"]
        for g in categories
        if g["name"] == group_name
        for c in g["categories"]
        if c["name"] == category_name
    )


@pytest.mark.asyncio
async def test_flag_with_category_sets_and_retroactively_fixes_siblings(client):
    await _upload_corrections_csv(client)
    txns = (await client.get("/api/transactions")).json()["transactions"]
    super_yuda_txns = [t for t in txns if t["description"] == "Super Yuda"]
    assert len(super_yuda_txns) == 2

    groceries_id = await _category_id(client, "Household Expenses", "Groceries")

    resp = await client.post(
        "/api/corrections",
        json={"transaction_id": super_yuda_txns[0]["id"], "category_id": groceries_id},
    )
    body = resp.json()
    assert body["ok"] is True
    assert body["correction"]["merchant_key"] == "super yuda"
    # both Super Yuda rows counted, including the one that was flagged
    assert body["updated_transactions"] == 2

    txns = (await client.get("/api/transactions")).json()["transactions"]
    super_yuda_txns = [t for t in txns if t["description"] == "Super Yuda"]
    weird = next(t for t in txns if t["description"] == "Weird Merchant")
    assert all(t["category"] == "Groceries" for t in super_yuda_txns)
    assert all(t["correction_status"] == "corrected" for t in super_yuda_txns)
    assert weird["correction_status"] is None


@pytest.mark.asyncio
async def test_flag_without_category_records_flag_only(client):
    await _upload_corrections_csv(client)
    txns = (await client.get("/api/transactions")).json()["transactions"]
    weird = next(t for t in txns if t["description"] == "Weird Merchant")

    resp = await client.post(
        "/api/corrections", json={"transaction_id": weird["id"], "category_id": None}
    )
    body = resp.json()
    assert body["ok"] is True
    assert body["correction"]["category_id"] is None
    assert body["updated_transactions"] == 0

    txns = (await client.get("/api/transactions")).json()["transactions"]
    weird = next(t for t in txns if t["description"] == "Weird Merchant")
    assert weird["category"] is None
    assert weird["correction_status"] == "flagged"


@pytest.mark.asyncio
async def test_flagging_same_merchant_twice_updates_existing_correction(client):
    await _upload_corrections_csv(client)
    txns = (await client.get("/api/transactions")).json()["transactions"]
    super_yuda_txns = [t for t in txns if t["description"] == "Super Yuda"]

    groceries_id = await _category_id(client, "Household Expenses", "Groceries")
    rent_id = await _category_id(client, "Home Expenses", "Rent")

    await client.post(
        "/api/corrections",
        json={"transaction_id": super_yuda_txns[0]["id"], "category_id": groceries_id},
    )
    resp = await client.post(
        "/api/corrections",
        json={"transaction_id": super_yuda_txns[1]["id"], "category_id": rent_id},
    )
    assert resp.json()["ok"] is True

    corrections = (await client.get("/api/corrections")).json()["corrections"]
    matching = [c for c in corrections if c["merchant_key"] == "super yuda"]
    assert len(matching) == 1
    assert matching[0]["category"] == "Rent"


@pytest.mark.asyncio
async def test_deleting_correction_clears_badge(client):
    await _upload_corrections_csv(client)
    txns = (await client.get("/api/transactions")).json()["transactions"]
    weird = next(t for t in txns if t["description"] == "Weird Merchant")

    create_resp = (
        await client.post("/api/corrections", json={"transaction_id": weird["id"], "category_id": None})
    ).json()
    correction_id = create_resp["correction"]["id"]

    del_resp = await client.delete(f"/api/corrections/{correction_id}")
    assert del_resp.json() == {"ok": True}

    txns = (await client.get("/api/transactions")).json()["transactions"]
    weird = next(t for t in txns if t["description"] == "Weird Merchant")
    assert weird["correction_status"] is None
    assert weird["correction_id"] is None


@pytest.mark.asyncio
async def test_categorize_backlog_skips_ai_for_corrected_merchant(client, db_session, monkeypatch):
    await _upload_corrections_csv(client)
    txns = (await client.get("/api/transactions")).json()["transactions"]
    super_yuda_txns = [t for t in txns if t["description"] == "Super Yuda"]

    groceries_id = await _category_id(client, "Household Expenses", "Groceries")
    await client.post(
        "/api/corrections",
        json={"transaction_id": super_yuda_txns[0]["id"], "category_id": groceries_id},
    )

    # Simulate an uncategorized transaction for an already-taught merchant
    # (e.g. one the retroactive scan didn't catch) by resetting its category
    # directly at the DB layer, bypassing the app.
    async with db_session() as session:
        result = await session.execute(select(Transaction).where(Transaction.description == "Super Yuda"))
        for txn in result.scalars().all():
            txn.category_id = None
        await session.commit()

    seen = []

    async def fake_categorizer(transactions):
        seen.extend(t["description"] for t in transactions)
        return [{"general_category": "Discretionary", "precise_category": "Classes"}] * len(transactions)

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr("app.routers.transactions.categorize_transactions", fake_categorizer)

    body = (await client.post("/api/transactions/categorize")).json()
    assert body["ok"] is True

    assert "Super Yuda" not in seen
    assert "Weird Merchant" in seen

    txns = (await client.get("/api/transactions")).json()["transactions"]
    super_yuda_txns = [t for t in txns if t["description"] == "Super Yuda"]
    assert all(t["category"] == "Groceries" for t in super_yuda_txns)

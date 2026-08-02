import io
from datetime import datetime
from decimal import Decimal

import pytest

from app.services import currency as currency_module


def _revolut_csv(date_str: str, description: str, amount: str, currency: str = "ILS") -> bytes:
    return (
        "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
        f"CARD_PAYMENT,Current,{date_str} 10:00:00,{date_str} 10:00:01,{description},{amount},0,{currency},COMPLETED,150.00\n"
    ).encode()


def _ca_csv(date_str: str, description: str, debit: str = "", credit: str = "") -> bytes:
    """date_str is "YYYY-MM-DD"; the CA parser expects "DD/MM/YYYY"."""
    year, month, day = date_str.split("-")
    ca_date = f"{day}/{month}/{year}"
    return (
        "Date;Libelle;Debit;Credit\n"
        f"{ca_date};{description};{debit};{credit}\n"
    ).encode()


def _leumi_csv(date_str: str, description: str, debit: str = "", credit: str = "") -> bytes:
    """date_str is "YYYY-MM-DD"; the Leumi parser expects "DD/MM/YYYY"."""
    year, month, day = date_str.split("-")
    leumi_date = f"{day}/{month}/{year}"
    return (
        ",,,,,,\n"
        "Bank Leumi - Account Transactions,,,,,\n"
        "Date,Description,Reference Number,Debit,Credit,NIS Balance\n"
        f"{leumi_date},{description},123456,{debit},{credit},1000.00\n"
    ).encode()


@pytest.mark.asyncio
async def test_empty_db_returns_empty_matches_and_zeroed_summary(client):
    body = (await client.get("/api/transfers")).json()
    assert body["matches"] == []
    assert body["summary"] == {
        "confirmed_count": 0,
        "suggested_count": 0,
        "rejected_count": 0,
        "total_transferred": "0",
        "total_fees": "0",
    }


@pytest.mark.asyncio
async def test_same_currency_pair_auto_detected_confirmed_and_hidden_from_transactions(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    await client.post(
        "/api/upload",
        files={"file": ("a.csv", io.BytesIO(_revolut_csv(today, "Move to Leumi", "-500.00")), "text/csv")},
    )
    await client.post(
        "/api/upload",
        files={"file": ("b.csv", io.BytesIO(_leumi_csv(today, "Move from Revolut", credit="500.00")), "text/csv")},
    )

    body = (await client.get("/api/transfers")).json()
    assert len(body["matches"]) == 1
    match = body["matches"][0]
    assert match["status"] == "confirmed"
    assert match["confidence"] == "high"
    assert body["summary"]["confirmed_count"] == 1

    txns = (await client.get("/api/transactions")).json()["transactions"]
    assert txns == []


@pytest.mark.asyncio
async def test_cross_currency_pair_detected_with_expected_confidence(client, monkeypatch):
    async def fake_rate(from_currency, to_currency, date_str=None):
        return Decimal("4")

    monkeypatch.setattr(currency_module, "get_exchange_rate", fake_rate)

    today = datetime.utcnow().strftime("%Y-%m-%d")
    await client.post(
        "/api/upload",
        files={"file": ("a.csv", io.BytesIO(_ca_csv(today, "Send abroad", debit="100,00")), "text/csv")},
    )
    await client.post(
        "/api/upload",
        files={"file": ("b.csv", io.BytesIO(_revolut_csv(today, "Received", "394.00", currency="ILS")), "text/csv")},
    )

    body = (await client.get("/api/transfers")).json()
    assert len(body["matches"]) == 1
    assert body["matches"][0]["confidence"] == "medium"
    assert body["matches"][0]["status"] == "suggested"


@pytest.mark.asyncio
async def test_detect_endpoint_is_idempotent(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    await client.post(
        "/api/upload",
        files={"file": ("a.csv", io.BytesIO(_revolut_csv(today, "Move to Leumi", "-500.00")), "text/csv")},
    )
    await client.post(
        "/api/upload",
        files={"file": ("b.csv", io.BytesIO(_leumi_csv(today, "Move from Revolut", credit="500.00")), "text/csv")},
    )

    resp1 = await client.post("/api/transfers/detect")
    resp2 = await client.post("/api/transfers/detect")

    assert resp1.json()["created"] == 0
    assert resp2.json()["created"] == 0

    body = (await client.get("/api/transfers")).json()
    assert len(body["matches"]) == 1


@pytest.mark.asyncio
async def test_rejecting_confirmed_match_restores_legs_and_blocks_recreation(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    await client.post(
        "/api/upload",
        files={"file": ("a.csv", io.BytesIO(_revolut_csv(today, "Move to Leumi", "-500.00")), "text/csv")},
    )
    await client.post(
        "/api/upload",
        files={"file": ("b.csv", io.BytesIO(_leumi_csv(today, "Move from Revolut", credit="500.00")), "text/csv")},
    )

    body = (await client.get("/api/transfers")).json()
    match_id = body["matches"][0]["id"]
    assert body["matches"][0]["status"] == "confirmed"

    reject_resp = await client.post(f"/api/transfers/{match_id}/reject")
    assert reject_resp.json()["match"]["status"] == "rejected"

    txns = (await client.get("/api/transactions")).json()["transactions"]
    assert len(txns) == 2

    detect_resp = await client.post("/api/transfers/detect")
    assert detect_resp.json()["created"] == 0

    body_after = (await client.get("/api/transfers")).json()
    assert len(body_after["matches"]) == 1
    assert body_after["matches"][0]["status"] == "rejected"


@pytest.mark.asyncio
async def test_confirming_suggested_match_hides_both_legs(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    await client.post(
        "/api/upload",
        files={"file": ("a.csv", io.BytesIO(_revolut_csv(today, "Move to Leumi", "-500.00")), "text/csv")},
    )
    await client.post(
        "/api/upload",
        files={"file": ("b.csv", io.BytesIO(_leumi_csv(today, "Move from Revolut", credit="490.00")), "text/csv")},
    )

    body = (await client.get("/api/transfers")).json()
    match = body["matches"][0]
    assert match["status"] == "suggested"

    txns_before = (await client.get("/api/transactions")).json()["transactions"]
    assert len(txns_before) == 2

    confirm_resp = await client.post(f"/api/transfers/{match['id']}/confirm")
    assert confirm_resp.json()["match"]["status"] == "confirmed"

    txns_after = (await client.get("/api/transactions")).json()["transactions"]
    assert txns_after == []


@pytest.mark.asyncio
async def test_fee_amount_reflects_shortfall_between_legs(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    await client.post(
        "/api/upload",
        files={"file": ("a.csv", io.BytesIO(_revolut_csv(today, "Move to Leumi", "-500.00")), "text/csv")},
    )
    await client.post(
        "/api/upload",
        files={"file": ("b.csv", io.BytesIO(_leumi_csv(today, "Move from Revolut", credit="490.00")), "text/csv")},
    )

    body = (await client.get("/api/transfers")).json()
    assert body["matches"][0]["fee_amount"] == "10.00"

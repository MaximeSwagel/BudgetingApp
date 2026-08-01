import io
from datetime import datetime, timedelta

import pytest


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


@pytest.mark.asyncio
async def test_analysis_empty(client):
    resp = await client.get("/api/analysis")
    assert resp.status_code == 200
    body = resp.json()
    assert body["base_currency"]
    assert body["days"] == 90
    assert body["daily"] == []
    assert body["categories"] == []
    assert body["duplicate_groups"] == []
    assert body["by_currency"] == []
    assert body["by_bank"] == []
    assert body["uncategorized_count"] == 0


@pytest.mark.asyncio
async def test_analysis_daily_aggregate_sum(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

    await client.post(
        "/api/upload",
        files={"file": ("a.csv", io.BytesIO(_revolut_csv(today, "Coffee", "-10.00")), "text/csv")},
    )
    await client.post(
        "/api/upload",
        files={"file": ("b.csv", io.BytesIO(_revolut_csv(today, "Lunch", "-15.00")), "text/csv")},
    )
    await client.post(
        "/api/upload",
        files={"file": ("c.csv", io.BytesIO(_revolut_csv(yesterday, "Dinner", "-20.00")), "text/csv")},
    )

    body = (await client.get("/api/analysis")).json()
    assert len(body["daily"]) == 2
    # oldest -> newest
    assert body["daily"][0]["date"] == yesterday
    assert body["daily"][0]["total"] == "20.00"
    assert body["daily"][1]["date"] == today
    assert body["daily"][1]["total"] == "25.00"


@pytest.mark.asyncio
async def test_analysis_daily_by_category_bucketing(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    await client.post(
        "/api/upload",
        files={"file": ("a.csv", io.BytesIO(_revolut_csv(today, "Mystery Shop", "-40.00")), "text/csv")},
    )

    body = (await client.get("/api/analysis")).json()
    day = body["daily"][0]
    assert day["total"] == "40.00"
    assert day["by_category"] == {"Uncategorized": "40.00"}


@pytest.mark.asyncio
async def test_analysis_category_distribution(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    await client.post(
        "/api/upload",
        files={"file": ("a.csv", io.BytesIO(_revolut_csv(today, "Tesco", "-25.00")), "text/csv")},
    )

    txns = (await client.get("/api/transactions", params={"uncategorized": "true"})).json()
    txn_id = txns["transactions"][0]["id"]

    categories = (await client.get("/api/categories")).json()
    groceries_id = next(
        c["id"]
        for g in categories
        if g["name"] == "Household Expenses"
        for c in g["categories"]
        if c["name"] == "Groceries"
    )
    await client.patch(f"/api/transactions/{txn_id}/category", json={"category_id": groceries_id})

    body = (await client.get("/api/analysis")).json()
    assert body["categories"] == [
        {"group": "Household Expenses", "category": "Groceries", "total": "25.00", "count": 1}
    ]
    assert body["uncategorized_count"] == 0


@pytest.mark.asyncio
async def test_analysis_uncategorized_count(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    await client.post(
        "/api/upload",
        files={"file": ("a.csv", io.BytesIO(_revolut_csv(today, "X", "-1.00")), "text/csv")},
    )
    await client.post(
        "/api/upload",
        files={"file": ("b.csv", io.BytesIO(_revolut_csv(today, "Y", "-2.00")), "text/csv")},
    )

    body = (await client.get("/api/analysis")).json()
    assert body["uncategorized_count"] == 2


@pytest.mark.asyncio
async def test_analysis_duplicate_detector(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    # Same date/amount/description, different bank (Revolut vs CA) -- the
    # strict 5-tuple import-time dedup does NOT skip this (currency/bank
    # differ), so both rows land in the table for the looser detector to
    # flag.
    await client.post(
        "/api/upload",
        files={"file": ("a.csv", io.BytesIO(_revolut_csv(today, "Tesco", "-40.00")), "text/csv")},
    )
    await client.post(
        "/api/upload",
        files={"file": ("b.csv", io.BytesIO(_ca_csv(today, "Tesco", debit="40,00")), "text/csv")},
    )

    body = (await client.get("/api/analysis")).json()
    assert len(body["duplicate_groups"]) == 1
    group = body["duplicate_groups"][0]
    assert group["date"] == today
    assert group["amount"] == "-40.00"
    assert group["description"] == "Tesco"
    assert group["count"] == 2
    assert set(group["banks"]) == {"Revolut", "CA"}


@pytest.mark.asyncio
async def test_analysis_currency_breakdown(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    await client.post(
        "/api/upload",
        files={"file": ("a.csv", io.BytesIO(_revolut_csv(today, "ILS Purchase", "-100.00", currency="ILS")), "text/csv")},
    )
    await client.post(
        "/api/upload",
        files={"file": ("b.csv", io.BytesIO(_ca_csv(today, "EUR Purchase", debit="50,00")), "text/csv")},
    )

    body = (await client.get("/api/analysis")).json()
    by_currency = {row["currency"]: row for row in body["by_currency"]}
    assert set(by_currency) == {"ILS", "EUR"}

    assert by_currency["ILS"]["count"] == 1
    assert by_currency["ILS"]["original_total"] == "-100.00"
    assert "converted_total" in by_currency["ILS"]

    assert by_currency["EUR"]["count"] == 1
    assert by_currency["EUR"]["original_total"] == "-50.00"
    # Conversion may hit the live Frankfurter API or the offline fallback
    # pivot -- assert the key exists without pinning the exact rate, so this
    # test stays network-independent.
    assert "converted_total" in by_currency["EUR"]


@pytest.mark.asyncio
async def test_analysis_by_bank_counts(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    await client.post(
        "/api/upload",
        files={"file": ("a.csv", io.BytesIO(_revolut_csv(today, "X", "-10.00")), "text/csv")},
    )
    await client.post(
        "/api/upload",
        files={"file": ("b.csv", io.BytesIO(_revolut_csv(today, "Y", "-20.00")), "text/csv")},
    )
    await client.post(
        "/api/upload",
        files={"file": ("c.csv", io.BytesIO(_ca_csv(today, "Z", debit="5,00")), "text/csv")},
    )

    body = (await client.get("/api/analysis")).json()
    by_bank = {row["bank"]: row for row in body["by_bank"]}

    # Revolut rows are already in base currency (ILS) -> exact, network-independent total.
    assert by_bank["Revolut"]["count"] == 2
    assert by_bank["Revolut"]["total"] == "30.00"

    # CA row is EUR -> converted total depends on live/fallback FX rate; only
    # assert the count to keep this network-independent.
    assert by_bank["CA"]["count"] == 1

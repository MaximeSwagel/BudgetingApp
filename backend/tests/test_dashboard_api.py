import io
from datetime import datetime

import pytest


def _csv_for(date_str: str, description: str, amount: str) -> bytes:
    return (
        "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
        f"CARD_PAYMENT,Current,{date_str} 10:00:00,{date_str} 10:00:01,{description},{amount},0,ILS,COMPLETED,150.00\n"
    ).encode()


@pytest.mark.asyncio
async def test_dashboard_empty(client):
    resp = await client.get("/api/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["base_currency"]
    assert len(body["months"]) == 6
    assert body["uncategorized_count"] == 0
    assert body["current_month"]["expenses"] == "0"
    assert body["current_month"]["by_group"] == []


@pytest.mark.asyncio
async def test_dashboard_counts_current_month_expense_and_uncategorized(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    resp = await client.post(
        "/api/upload",
        files={"file": ("now.csv", io.BytesIO(_csv_for(today, "Groceries Store", "-40.00")), "text/csv")},
    )
    assert resp.json()["imported"] == 1

    body = (await client.get("/api/dashboard")).json()
    assert body["current_month"]["expenses"] == "40.00"
    # no OpenAI key in tests -> transaction stays uncategorized (NULL), not
    # silently dumped into a wrong category group
    assert body["uncategorized_count"] == 1
    assert body["current_month"]["by_group"] == []


@pytest.mark.asyncio
async def test_dashboard_income_and_expense_split(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    await client.post(
        "/api/upload",
        files={"file": ("a.csv", io.BytesIO(_csv_for(today, "Salary", "1000.00")), "text/csv")},
    )
    await client.post(
        "/api/upload",
        files={"file": ("b.csv", io.BytesIO(_csv_for(today, "Rent payment", "-300.00")), "text/csv")},
    )

    body = (await client.get("/api/dashboard")).json()
    assert body["current_month"]["income"] == "1000.00"
    assert body["current_month"]["expenses"] == "300.00"


@pytest.mark.asyncio
async def test_dashboard_by_group_populated_once_categorized(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    upload = await client.post(
        "/api/upload",
        files={"file": ("a.csv", io.BytesIO(_csv_for(today, "Tesco", "-25.00")), "text/csv")},
    )
    assert upload.json()["imported"] == 1

    txns = (await client.get("/api/transactions", params={"uncategorized": "true"})).json()
    assert txns["total"] == 1
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

    body = (await client.get("/api/dashboard")).json()
    assert body["uncategorized_count"] == 0
    assert body["current_month"]["by_group"] == [{"group": "Household Expenses", "total": "25.00"}]

    # and the uncategorized filter no longer matches it
    txns = (await client.get("/api/transactions", params={"uncategorized": "true"})).json()
    assert txns["total"] == 0

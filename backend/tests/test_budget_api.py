import io

import pytest

JAN_EXPENSE_CSV = (
    "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
    "CARD_PAYMENT,Current,2026-01-05 10:00:00,2026-01-05 10:00:01,Tesco,-20.00,0,ILS,COMPLETED,150.00\n"
)

FEB_EXPENSE_CSV = (
    "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
    "CARD_PAYMENT,Current,2026-02-10 10:00:00,2026-02-10 10:00:01,Sainsburys,-30.00,0,ILS,COMPLETED,120.00\n"
)


@pytest.mark.asyncio
async def test_budget_summary_empty_when_no_transactions(client):
    resp = await client.get("/api/budget/summary", params={"year": 2026})
    assert resp.status_code == 200
    body = resp.json()
    assert body["year"] == 2026
    assert body["total_expense_annual"] == "0"
    assert len(body["groups"]) > 0


@pytest.mark.asyncio
async def test_budget_summary_aggregates_expenses_by_month(client):
    await client.post("/api/upload", files={"file": ("a.csv", io.BytesIO(JAN_EXPENSE_CSV.encode()), "text/csv")})
    await client.post("/api/upload", files={"file": ("b.csv", io.BytesIO(FEB_EXPENSE_CSV.encode()), "text/csv")})

    resp = await client.get("/api/budget/summary", params={"year": 2026})
    body = resp.json()

    assert body["total_expense_monthly"]["1"] == "-20.00"
    assert body["total_expense_monthly"]["2"] == "-30.00"
    assert body["total_expense_annual"] == "-50.00"


@pytest.mark.asyncio
async def test_budget_summary_filters_by_year(client):
    await client.post("/api/upload", files={"file": ("a.csv", io.BytesIO(JAN_EXPENSE_CSV.encode()), "text/csv")})

    resp = await client.get("/api/budget/summary", params={"year": 2025})
    body = resp.json()

    assert body["total_expense_annual"] == "0"


@pytest.mark.asyncio
async def test_set_and_read_budget_target(client):
    categories_resp = await client.get("/api/categories")
    first_category_id = categories_resp.json()[0]["categories"][0]["id"]

    resp = await client.post(
        "/api/budget/targets",
        json={"category_id": first_category_id, "year": 2026, "month": 1, "amount": "100.00"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    summary = await client.get("/api/budget/summary", params={"year": 2026})
    groups = summary.json()["groups"]
    target_found = any(
        cat["targets"].get("1") == "100.00"
        for group in groups
        for cat in group["categories"]
        if cat["category_id"] == first_category_id
    )
    assert target_found

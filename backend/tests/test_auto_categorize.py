import io

import pytest

from app.config import settings

CSV = (
    "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
    "CARD_PAYMENT,Current,2026-01-05 10:00:00,2026-01-05 10:00:01,Tesco,-20.00,0,ILS,COMPLETED,150.00\n"
    "CARD_PAYMENT,Current,2026-01-06 11:00:00,2026-01-06 11:00:01,Weird Merchant,-8.50,0,ILS,COMPLETED,141.50\n"
)


async def _upload(client):
    resp = await client.post("/api/upload", files={"file": ("a.csv", io.BytesIO(CSV.encode()), "text/csv")})
    return resp.json()


@pytest.mark.asyncio
async def test_categorize_requires_api_key(client):
    resp = await client.post("/api/transactions/categorize")
    assert "error" in resp.json()


@pytest.mark.asyncio
async def test_categorize_nothing_to_do(client, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    body = (await client.post("/api/transactions/categorize")).json()
    assert body == {"ok": True, "processed": 0, "categorized": 0, "remaining": 0}


@pytest.mark.asyncio
async def test_categorize_assigns_backlog(client, monkeypatch):
    await _upload(client)  # no key -> both stay uncategorized

    async def fake_categorizer(transactions):
        results = []
        for t in transactions:
            if t["description"] == "Tesco":
                results.append({"general_category": "Household Expenses", "precise_category": "Groceries"})
            else:
                results.append({"general_category": "Uncategorized", "precise_category": "Uncategorized"})
        return results

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr("app.routers.transactions.categorize_transactions", fake_categorizer)

    body = (await client.post("/api/transactions/categorize")).json()
    assert body["ok"] is True
    assert body["processed"] == 2
    assert body["categorized"] == 1
    assert body["remaining"] == 1

    txns = (await client.get("/api/transactions")).json()["transactions"]
    by_desc = {t["description"]: t for t in txns}
    assert by_desc["Tesco"]["category"] == "Groceries"
    assert by_desc["Weird Merchant"]["category"] is None


@pytest.mark.asyncio
async def test_categorize_leaves_manual_assignments_alone(client, monkeypatch):
    await _upload(client)

    # manually categorize Tesco first
    txns = (await client.get("/api/transactions", params={"uncategorized": "true"})).json()["transactions"]
    tesco = next(t for t in txns if t["description"] == "Tesco")
    categories = (await client.get("/api/categories")).json()
    rent_id = next(
        c["id"] for g in categories if g["name"] == "Home Expenses" for c in g["categories"] if c["name"] == "Rent"
    )
    await client.patch(f"/api/transactions/{tesco['id']}/category", json={"category_id": rent_id})

    seen = []

    async def fake_categorizer(transactions):
        seen.extend(t["description"] for t in transactions)
        return [{"general_category": "Discretionary", "precise_category": "Classes"}] * len(transactions)

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr("app.routers.transactions.categorize_transactions", fake_categorizer)

    body = (await client.post("/api/transactions/categorize")).json()
    # only the still-uncategorized transaction was sent to the categorizer
    assert seen == ["Weird Merchant"]
    assert body["processed"] == 1

    txns = (await client.get("/api/transactions")).json()["transactions"]
    by_desc = {t["description"]: t for t in txns}
    assert by_desc["Tesco"]["category"] == "Rent"  # untouched
    assert by_desc["Weird Merchant"]["category"] == "Classes"

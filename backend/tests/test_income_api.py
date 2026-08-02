import io
from datetime import datetime, timedelta

import pytest


def _revolut_csv(date_str: str, description: str, amount: str, currency: str = "ILS") -> bytes:
    """Positive `amount` -> income row (is_expense=False). Mirrors
    test_analysis_api.py's helper."""
    return (
        "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
        f"CARD_PAYMENT,Current,{date_str} 10:00:00,{date_str} 10:00:01,{description},{amount},0,{currency},COMPLETED,150.00\n"
    ).encode()


async def _upload(client, filename: str, date_str: str, description: str, amount: str):
    csv_bytes = _revolut_csv(date_str, description, amount)
    return await client.post("/api/upload", files={"file": (filename, io.BytesIO(csv_bytes), "text/csv")})


@pytest.mark.asyncio
async def test_income_empty(client):
    resp = await client.get("/api/income")
    assert resp.status_code == 200
    body = resp.json()
    assert body["streams"] == []
    assert body["one_offs"] == []
    assert body["totals"]["transaction_count"] == 0
    assert len(body["monthly"]) == 12
    assert body["base_currency"]


@pytest.mark.asyncio
async def test_income_recognizes_a_recurring_monthly_stream(client):
    # 30-day steps land squarely inside the monthly cadence window.
    today = datetime.utcnow().date()
    dates = [today - timedelta(days=30 * k) for k in (3, 2, 1, 0)]
    dates.sort()

    for i, d in enumerate(dates):
        await _upload(client, f"salary{i}.csv", d.strftime("%Y-%m-%d"), "ACME CORP SALARY", "10000.00")

    body = (await client.get("/api/income")).json()
    assert len(body["streams"]) == 1
    stream = body["streams"][0]
    assert stream["cadence"] == "monthly"
    assert stream["occurrence_count"] == 4
    assert stream["expected_next"] >= dates[-1].isoformat()


@pytest.mark.asyncio
async def test_income_one_off_gift_is_not_a_stream(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    resp = await _upload(client, "gift.csv", today, "Birthday gift", "500.00")
    assert resp.json()["imported"] == 1

    body = (await client.get("/api/income")).json()
    assert body["streams"] == []
    assert len(body["one_offs"]) == 1
    one_off_id = body["one_offs"][0]["id"]

    for stream in body["streams"]:
        occurrence_ids = {o["id"] for o in stream["occurrences"]}
        assert one_off_id not in occurrence_ids


@pytest.mark.asyncio
async def test_income_excludes_expense_rows(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    await _upload(client, "expense.csv", today, "Groceries", "-50.00")

    body = (await client.get("/api/income")).json()
    assert body["streams"] == []
    assert body["one_offs"] == []
    assert body["totals"]["transaction_count"] == 0


@pytest.mark.asyncio
async def test_income_this_month_total_matches_current_month_income(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    await _upload(client, "a.csv", today, "Freelance payment", "300.00")
    await _upload(client, "b.csv", today, "Consulting fee", "200.00")

    body = (await client.get("/api/income")).json()
    assert body["totals"]["this_month"] == "500.00"


@pytest.mark.asyncio
async def test_income_monetary_fields_are_strings(client):
    today = datetime.utcnow().date()
    dates = [today - timedelta(days=30 * k) for k in (2, 1, 0)]
    for i, d in enumerate(dates):
        await _upload(client, f"pay{i}.csv", d.strftime("%Y-%m-%d"), "Regular Payer", "1000.00")

    body = (await client.get("/api/income")).json()
    assert isinstance(body["totals"]["ytd"], str)
    assert len(body["streams"]) == 1
    assert isinstance(body["streams"][0]["latest_amount"], str)

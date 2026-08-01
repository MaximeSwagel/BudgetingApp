import io

import pytest


def _revolut_csv(completed_at: str, description: str = "Tesco", amount: str = "-20.00") -> bytes:
    return (
        "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
        f"CARD_PAYMENT,Current,{completed_at},{completed_at},{description},{amount},0,GBP,COMPLETED,150.00\n"
    ).encode()


@pytest.mark.asyncio
async def test_date_filter_narrows_results_to_the_requested_range(client):
    files = {"file": ("in_range.csv", io.BytesIO(_revolut_csv("2026-01-15 10:00:00", "In range")), "text/csv")}
    await client.post("/api/upload", files=files)

    files = {"file": ("out_of_range.csv", io.BytesIO(_revolut_csv("2026-06-20 10:00:00", "Out of range")), "text/csv")}
    await client.post("/api/upload", files=files)

    resp = await client.get(
        "/api/transactions",
        params={"date_from": "2026-01-01", "date_to": "2026-03-31"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["transactions"][0]["description"] == "In range"


@pytest.mark.asyncio
async def test_date_filter_is_inclusive_of_the_end_date(client):
    """A transaction that happened later in the day on date_to must still be
    included -- date_to should mean "through the end of that day", not an
    exact midnight cutoff. This is the actual reported bug: transactions
    with a non-midnight timestamp on the boundary day were silently
    excluded, making the filter look like it "did nothing" for common
    same-day / recent-range queries."""
    files = {
        "file": (
            "same_day.csv",
            io.BytesIO(_revolut_csv("2026-01-05 14:30:00", "Afternoon purchase")),
            "text/csv",
        )
    }
    await client.post("/api/upload", files=files)

    resp = await client.get(
        "/api/transactions",
        params={"date_from": "2026-01-05", "date_to": "2026-01-05"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["transactions"][0]["description"] == "Afternoon purchase"

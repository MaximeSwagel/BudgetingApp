import io

import pytest


REVOLUT_EN_CSV = (
    "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
    "CARD_PAYMENT,Current,2026-01-05 10:00:00,2026-01-05 10:00:01,Tesco,-20.00,0,GBP,COMPLETED,150.00\n"
)


@pytest.mark.asyncio
async def test_upload_csv_imports_transactions(client):
    files = {"file": ("revolut.csv", io.BytesIO(REVOLUT_EN_CSV.encode()), "text/csv")}
    resp = await client.post("/api/upload", files=files)

    assert resp.status_code == 200
    body = resp.json()
    assert body["format_detected"] == "revolut_en"
    assert body["imported"] == 1
    assert body["duplicates_skipped"] == 0


@pytest.mark.asyncio
async def test_upload_csv_skips_duplicates_on_second_import(client):
    files = {"file": ("revolut.csv", io.BytesIO(REVOLUT_EN_CSV.encode()), "text/csv")}
    await client.post("/api/upload", files=files)

    files = {"file": ("revolut.csv", io.BytesIO(REVOLUT_EN_CSV.encode()), "text/csv")}
    resp = await client.post("/api/upload", files=files)

    body = resp.json()
    assert body["imported"] == 0
    assert body["duplicates_skipped"] == 1


@pytest.mark.asyncio
async def test_upload_csv_unrecognized_format_raises(client):
    # detect_bank_format() raises ValueError for an unrecognized header, and upload_csv()
    # has no try/except around that call, so it propagates rather than returning a JSON error.
    files = {"file": ("weird.csv", io.BytesIO(b"foo,bar\n1,2\n"), "text/csv")}
    with pytest.raises(ValueError, match="Unrecognized CSV format"):
        await client.post("/api/upload", files=files)


@pytest.mark.asyncio
async def test_uploaded_transaction_appears_in_transaction_list(client):
    files = {"file": ("revolut.csv", io.BytesIO(REVOLUT_EN_CSV.encode()), "text/csv")}
    await client.post("/api/upload", files=files)

    resp = await client.get("/api/transactions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["transactions"][0]["description"] == "Tesco"

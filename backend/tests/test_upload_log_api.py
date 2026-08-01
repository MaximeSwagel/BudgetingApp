import io

import pytest

REVOLUT_EN_CSV = (
    "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
    "CARD_PAYMENT,Current,2026-01-05 10:00:00,2026-01-05 10:00:01,Tesco,-20.00,0,GBP,COMPLETED,150.00\n"
)


@pytest.mark.asyncio
async def test_successful_upload_records_success_log(client):
    files = {"file": ("revolut.csv", io.BytesIO(REVOLUT_EN_CSV.encode()), "text/csv")}
    await client.post("/api/upload", files=files)

    logs = (await client.get("/api/upload/logs")).json()["logs"]
    assert len(logs) == 1
    log = logs[0]
    assert log["status"] == "success"
    assert log["filename"] == "revolut.csv"
    assert log["bank"] == "Revolut"
    assert log["format_detected"] == "revolut_en"
    assert log["rows_parsed"] == 1
    assert log["rows_imported"] == 1
    assert log["rows_skipped"] == 0
    assert log["error"] is None


@pytest.mark.asyncio
async def test_duplicate_reupload_records_rows_skipped(client):
    files = {"file": ("revolut.csv", io.BytesIO(REVOLUT_EN_CSV.encode()), "text/csv")}
    await client.post("/api/upload", files=files)

    files = {"file": ("revolut.csv", io.BytesIO(REVOLUT_EN_CSV.encode()), "text/csv")}
    await client.post("/api/upload", files=files)

    logs = (await client.get("/api/upload/logs")).json()["logs"]
    assert len(logs) == 2
    latest = logs[0]
    assert latest["status"] == "success"
    assert latest["rows_imported"] == 0
    assert latest["rows_skipped"] == 1


@pytest.mark.asyncio
async def test_unrecognized_format_records_failed_log(client):
    files = {"file": ("weird.csv", io.BytesIO(b"foo,bar\n1,2\n"), "text/csv")}
    resp = await client.post("/api/upload", files=files)
    assert resp.status_code == 200
    assert "error" in resp.json()

    logs = (await client.get("/api/upload/logs")).json()["logs"]
    assert len(logs) == 1
    assert logs[0]["status"] == "failed"
    assert logs[0]["filename"] == "weird.csv"
    assert logs[0]["error"] is not None


@pytest.mark.asyncio
async def test_upload_logs_returned_newest_first(client):
    files_a = {"file": ("a.csv", io.BytesIO(REVOLUT_EN_CSV.encode()), "text/csv")}
    await client.post("/api/upload", files=files_a)

    files_bad = {"file": ("bad.csv", io.BytesIO(b"foo,bar\n1,2\n"), "text/csv")}
    await client.post("/api/upload", files=files_bad)

    logs = (await client.get("/api/upload/logs")).json()["logs"]
    assert len(logs) == 2
    assert logs[0]["filename"] == "bad.csv"
    assert logs[1]["filename"] == "a.csv"

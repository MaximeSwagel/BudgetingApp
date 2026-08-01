import io

import pytest

from app.config import settings

CSV = (
    "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
    "CARD_PAYMENT,Current,2026-01-05 10:00:00,2026-01-05 10:00:01,Tesco,-20.00,0,ILS,COMPLETED,150.00\n"
    "CARD_PAYMENT,Current,2026-01-06 11:00:00,2026-01-06 11:00:01,Cafe,-8.50,0,ILS,COMPLETED,141.50\n"
)


async def _upload(client, name="a.csv", csv=CSV):
    resp = await client.post("/api/upload", files={"file": (name, io.BytesIO(csv.encode()), "text/csv")})
    return resp.json()


@pytest.mark.asyncio
async def test_undo_import_removes_batch_transactions(client):
    result = await _upload(client)
    assert result["imported"] == 2
    batch_id = result["batch_id"]

    resp = await client.delete(f"/api/upload/batches/{batch_id}")
    body = resp.json()
    assert body["ok"] is True
    assert body["deleted"] == 2

    txns = (await client.get("/api/transactions")).json()
    assert txns["total"] == 0


@pytest.mark.asyncio
async def test_undo_import_is_reuploadable(client):
    """After undoing, the same CSV imports again (dedup rows are gone)."""
    first = await _upload(client)
    await client.delete(f"/api/upload/batches/{first['batch_id']}")

    second = await _upload(client)
    assert second["imported"] == 2
    assert second["duplicates_skipped"] == 0


@pytest.mark.asyncio
async def test_undo_unknown_batch_returns_error(client):
    resp = await client.delete("/api/upload/batches/9999")
    assert "error" in resp.json()


@pytest.mark.asyncio
async def test_undo_only_removes_its_own_batch(client):
    first = await _upload(client)
    other_csv = CSV.replace("Tesco", "Lidl").replace("Cafe", "Bakery")
    second = await _upload(client, name="b.csv", csv=other_csv)

    await client.delete(f"/api/upload/batches/{first['batch_id']}")

    txns = (await client.get("/api/transactions")).json()
    assert txns["total"] == 2
    descriptions = {t["description"] for t in txns["transactions"]}
    assert descriptions == {"Lidl", "Bakery"}
    assert all(t is not None for t in [second["batch_id"]])


@pytest.mark.asyncio
async def test_reset_forbidden_by_default(client):
    features = (await client.get("/api/admin/features")).json()
    assert features["data_reset"] is False

    resp = await client.post("/api/admin/reset")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reset_clears_everything_when_enabled(client, monkeypatch):
    monkeypatch.setattr(settings, "allow_data_reset", True)

    await _upload(client)
    features = (await client.get("/api/admin/features")).json()
    assert features["data_reset"] is True

    resp = await client.post("/api/admin/reset")
    assert resp.json() == {"ok": True, "deleted": 2}

    txns = (await client.get("/api/transactions")).json()
    assert txns["total"] == 0

    # categories survive a reset
    categories = (await client.get("/api/categories")).json()
    assert len(categories) > 0

"""Upload timing events: shape, field order, and the no-sensitive-data rule."""

import io
import logging
import re
from decimal import Decimal

import pytest

REVOLUT_EN_CSV = (
    "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
    "CARD_PAYMENT,Current,2026-01-05 10:00:00,2026-01-05 10:00:01,Tesco,-20.00,0,GBP,COMPLETED,150.00\n"
)


@pytest.fixture(autouse=True)
def _stubs(monkeypatch):
    async def fake_categorize(transactions):
        return [{"general_category": "Uncategorized", "precise_category": "Uncategorized"} for _ in transactions]

    async def fake_convert(amount, from_cur, to_cur, date_str):
        return amount, Decimal("1")

    monkeypatch.setattr("app.routers.upload.categorize_transactions", fake_categorize)
    monkeypatch.setattr("app.routers.upload.convert_amount", fake_convert)


def _messages(caplog, name="app.routers.upload"):
    return [r for r in caplog.records if r.name == name]


async def test_successful_upload_emits_parse_categorize_and_summary(client, caplog):
    caplog.set_level(logging.INFO)
    resp = await client.post("/api/upload", files={"file": ("r.csv", io.BytesIO(REVOLUT_EN_CSV.encode()), "text/csv")})
    assert resp.status_code == 200
    msgs = [r.getMessage() for r in _messages(caplog)]

    assert any(re.match(r"^event=csv_parse parser=revolut_en rows=1 bytes=\d+ ms=\d+\.\d$", m) for m in msgs)
    assert any(re.match(r"^event=csv_categorize rows=1 ms=\d+\.\d$", m) for m in msgs)
    assert any(
        re.match(
            r"^event=csv_upload status=ok parser=revolut_en bank=Revolut rows_parsed=1 rows_imported=1 "
            r"duplicates=0 fees=0 transfers=\d+ parse_ms=\d+\.\d categorize_ms=\d+\.\d persist_ms=\d+\.\d "
            r"transfer_scan_ms=\d+\.\d ms=\d+\.\d$",
            m,
        )
        for m in msgs
    )
    for r in caplog.records:
        assert "Tesco" not in r.getMessage()
        assert "-20.00" not in r.getMessage()


async def test_failed_upload_logs_fixed_reason_without_content(client, caplog):
    caplog.set_level(logging.INFO)
    await client.post("/api/upload", files={"file": ("x.csv", io.BytesIO(b"foo,bar\n1,2\n"), "text/csv")})
    warnings = [r for r in _messages(caplog) if r.levelno == logging.WARNING]
    assert any(
        re.match(r"^event=csv_upload status=failed reason=unrecognized_format parser=- ms=\d+\.\d$", r.getMessage())
        for r in warnings
    )
    for r in caplog.records:
        assert "foo,bar" not in r.getMessage()

import io
import logging
import re
from collections import Counter
from decimal import Decimal

import pytest

from app.config import settings
from app.models import CategoryGroup
from app.repositories import CategoryGroupRepository, CategoryRepository
from app.services import classifier
from app.services.classifier import log_category_fallbacks, resolve_category_id

BAD = {"general_category": "Household Expenses", "precise_category": "Nonsense Tesco Thing"}
UPLOAD_CSV = (
    "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
    "CARD_PAYMENT,Current,2026-01-05 10:00:00,2026-01-05 10:00:01,Tesco,-20.00,0,ILS,COMPLETED,150.00\n"
    "CARD_PAYMENT,Current,2026-01-06 11:00:00,2026-01-06 11:00:01,Weird Merchant,-8.50,0,ILS,COMPLETED,141.50\n"
)


def _fallback_lines(caplog):
    return [r.getMessage() for r in caplog.records if "event=category_fallback" in r.getMessage()]


async def _resolve(db_session, cat_data, fallbacks=None):
    async with db_session() as s:
        groups, cats = CategoryGroupRepository(s), CategoryRepository(s)
        if fallbacks is None:
            return await resolve_category_id(cat_data, groups, cats)
        return await resolve_category_id(cat_data, groups, cats, fallbacks=fallbacks)


async def test_unknown_category_falls_back_to_first_in_group_and_counts(db_session):
    async with db_session() as s:
        group = await CategoryGroupRepository(s).get_by_name("Household Expenses")
        first = await CategoryRepository(s).first_in_group(group.id)
    counter = Counter()

    assert await _resolve(db_session, BAD, counter) == first.id
    assert counter == Counter(unknown_category=1)
    assert await _resolve(db_session, BAD) == first.id


async def test_unknown_group_returns_none_and_counts(db_session):
    counter = Counter()
    assert await _resolve(db_session, {"general_category": "Nope", "precise_category": "x"}, counter) is None
    assert counter == Counter(unknown_group=1)


async def test_empty_group_returns_none_and_counts(db_session):
    async with db_session() as s:
        s.add(CategoryGroup(name="Hollow", display_order=50))
        await s.commit()
    counter = Counter()
    assert await _resolve(db_session, {"general_category": "Hollow", "precise_category": "x"}, counter) is None
    assert counter == Counter(empty_group=1)


async def test_exact_match_and_uncategorized_count_nothing(db_session):
    counter = Counter()
    good = {"general_category": "Household Expenses", "precise_category": "Groceries"}
    assert await _resolve(db_session, good, counter) is not None
    unc = {"general_category": "Uncategorized", "precise_category": "Uncategorized"}
    assert await _resolve(db_session, unc, counter) is None
    assert sum(counter.values()) == 0


def test_log_category_fallbacks_silent_when_empty(caplog):
    caplog.set_level(logging.INFO)
    log_category_fallbacks(Counter(), source="upload", rows=3)
    assert _fallback_lines(caplog) == []


def test_log_category_fallbacks_line(caplog):
    caplog.set_level(logging.INFO)
    log_category_fallbacks(Counter(unknown_category=1, unknown_group=1), source="upload", rows=3)
    (line,) = _fallback_lines(caplog)
    assert re.match(
        r"^event=category_fallback source=upload rows=3 unknown_category=1 empty_group=0 unknown_group=1$", line
    )
    assert [r.levelno for r in caplog.records if "category_fallback" in r.getMessage()] == [logging.WARNING]


async def test_auto_categorize_logs_fallback_counts(client, monkeypatch, caplog):
    await client.post("/api/upload", files={"file": ("a.csv", io.BytesIO(UPLOAD_CSV.encode()), "text/csv")})

    async def fake(transactions):
        return [dict(BAD) for _ in transactions]

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr("app.routers.transactions.categorize_transactions", fake)
    caplog.set_level(logging.INFO)

    body = (await client.post("/api/transactions/categorize")).json()

    assert body["categorized"] == 2
    (line,) = _fallback_lines(caplog)
    assert line == (
        "event=category_fallback source=auto_categorize rows=2 unknown_category=2 empty_group=0 unknown_group=0"
    )
    assert all("Tesco" not in r.getMessage() and "Nonsense" not in r.getMessage() for r in caplog.records)


async def test_upload_logs_fallback_counts(client, monkeypatch, caplog):
    async def fake(transactions):
        return [dict(BAD) for _ in transactions]

    async def convert(amount, from_cur, to_cur, date_str):
        return amount, Decimal("1")

    monkeypatch.setattr("app.routers.upload.categorize_transactions", fake)
    monkeypatch.setattr("app.routers.upload.convert_amount", convert)
    caplog.set_level(logging.INFO)

    resp = await client.post("/api/upload", files={"file": ("a.csv", io.BytesIO(UPLOAD_CSV.encode()), "text/csv")})

    assert resp.status_code == 200
    (line,) = _fallback_lines(caplog)
    assert line == "event=category_fallback source=upload rows=2 unknown_category=2 empty_group=0 unknown_group=0"
    assert all("Tesco" not in r.getMessage() and "Nonsense" not in r.getMessage() for r in caplog.records)

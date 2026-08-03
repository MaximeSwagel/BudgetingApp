import io
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import CategoryGroupTarget

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


async def _categorize_all(client, category_id: int):
    txns = (await client.get("/api/transactions", params={"uncategorized": "true", "page_size": "200"})).json()
    for t in txns["transactions"]:
        await client.patch(f"/api/transactions/{t['id']}/category", json={"category_id": category_id})


@pytest.mark.asyncio
async def test_budget_summary_aggregates_expenses_by_month(client):
    await client.post("/api/upload", files={"file": ("a.csv", io.BytesIO(JAN_EXPENSE_CSV.encode()), "text/csv")})
    await client.post("/api/upload", files={"file": ("b.csv", io.BytesIO(FEB_EXPENSE_CSV.encode()), "text/csv")})

    # uploads without an OpenAI key stay uncategorized and are absent from the
    # (category-joined) budget grid until assigned a category
    categories_resp = await client.get("/api/categories")
    first_category_id = categories_resp.json()[0]["categories"][0]["id"]
    await _categorize_all(client, first_category_id)

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
async def test_summary_has_no_target_when_none_set(client):
    summary = await client.get("/api/budget/summary", params={"year": 2026})
    groups = summary.json()["groups"]
    assert len(groups) > 0
    for group in groups:
        assert group["current_target"] is None
        assert all(group["targets"].get(str(m)) is None for m in range(1, 13))


@pytest.mark.asyncio
async def test_set_group_target_applies_to_every_month(client):
    categories_resp = await client.get("/api/categories")
    group_id = categories_resp.json()[0]["id"]

    resp = await client.post(
        "/api/budget/group-targets", json={"group_id": group_id, "amount": "2000.00"}
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    today = date.today()
    summary = await client.get("/api/budget/summary", params={"year": today.year})
    groups = summary.json()["groups"]
    group = next(g for g in groups if g["group_id"] == group_id)

    assert group["current_target"] == "2000.00"
    for m in range(1, 13):
        assert group["targets"][str(m)] == "2000.00"


@pytest.mark.asyncio
async def test_setting_target_twice_in_same_month_updates_one_row(client, db_session):
    categories_resp = await client.get("/api/categories")
    group_id = categories_resp.json()[0]["id"]

    await client.post("/api/budget/group-targets", json={"group_id": group_id, "amount": "2000.00"})
    resp = await client.post(
        "/api/budget/group-targets", json={"group_id": group_id, "amount": "2500.00"}
    )
    assert resp.status_code == 200

    today = date.today()
    summary = await client.get("/api/budget/summary", params={"year": today.year})
    group = next(g for g in summary.json()["groups"] if g["group_id"] == group_id)
    assert group["current_target"] == "2500.00"
    for m in range(1, 13):
        assert group["targets"][str(m)] == "2500.00"

    async with db_session() as session:
        result = await session.execute(
            select(CategoryGroupTarget).where(CategoryGroupTarget.group_id == group_id)
        )
        rows = result.scalars().all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_latest_target_row_applies_to_every_month_and_year(client, db_session):
    categories_resp = await client.get("/api/categories")
    group_id = categories_resp.json()[0]["id"]

    async with db_session() as session:
        session.add(
            CategoryGroupTarget(
                group_id=group_id, amount=Decimal("500.00"), effective_month=date(2026, 1, 1)
            )
        )
        session.add(
            CategoryGroupTarget(
                group_id=group_id, amount=Decimal("800.00"), effective_month=date(2026, 6, 1)
            )
        )
        await session.commit()

    summary_2026 = await client.get("/api/budget/summary", params={"year": 2026})
    group_2026 = next(g for g in summary_2026.json()["groups"] if g["group_id"] == group_id)
    for m in range(1, 13):
        assert group_2026["targets"][str(m)] == "800.00"

    summary_2025 = await client.get("/api/budget/summary", params={"year": 2025})
    group_2025 = next(g for g in summary_2025.json()["groups"] if g["group_id"] == group_id)
    for m in range(1, 13):
        assert group_2025["targets"][str(m)] == "800.00"

    summary_2027 = await client.get("/api/budget/summary", params={"year": 2027})
    group_2027 = next(g for g in summary_2027.json()["groups"] if g["group_id"] == group_id)
    for m in range(1, 13):
        assert group_2027["targets"][str(m)] == "800.00"


@pytest.mark.asyncio
async def test_clear_group_target_clears_every_month(client):
    categories_resp = await client.get("/api/categories")
    group_id = categories_resp.json()[0]["id"]

    await client.post("/api/budget/group-targets", json={"group_id": group_id, "amount": "2000.00"})
    del_resp = await client.delete(f"/api/budget/group-targets/{group_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["ok"] is True

    today = date.today()
    summary = await client.get("/api/budget/summary", params={"year": today.year})
    group = next(g for g in summary.json()["groups"] if g["group_id"] == group_id)

    assert group["current_target"] is None
    for m in range(1, 13):
        assert group["targets"][str(m)] is None

    summary_2025 = await client.get("/api/budget/summary", params={"year": 2025})
    group_2025 = next(g for g in summary_2025.json()["groups"] if g["group_id"] == group_id)
    for m in range(1, 13):
        assert group_2025["targets"][str(m)] is None


@pytest.mark.asyncio
async def test_group_target_validation(client):
    categories_resp = await client.get("/api/categories")
    group_id = categories_resp.json()[0]["id"]

    missing_group = await client.post(
        "/api/budget/group-targets", json={"group_id": 999999, "amount": "10.00"}
    )
    assert missing_group.status_code == 404

    negative = await client.post(
        "/api/budget/group-targets", json={"group_id": group_id, "amount": "-10.00"}
    )
    assert negative.status_code == 400

    non_numeric = await client.post(
        "/api/budget/group-targets", json={"group_id": group_id, "amount": "not-a-number"}
    )
    assert non_numeric.status_code == 400


@pytest.mark.asyncio
async def test_targets_are_group_level_only(client):
    summary = await client.get("/api/budget/summary", params={"year": 2026})
    for group in summary.json()["groups"]:
        for cat in group["categories"]:
            assert "targets" not in cat

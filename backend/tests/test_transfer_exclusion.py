import io
from datetime import datetime
from decimal import Decimal

import pytest

from app.models import InternalTransferMatch


def _revolut_csv(date_str: str, description: str, amount: str, currency: str = "ILS") -> bytes:
    return (
        "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
        f"CARD_PAYMENT,Current,{date_str} 10:00:00,{date_str} 10:00:01,{description},{amount},0,{currency},COMPLETED,150.00\n"
    ).encode()


def _leumi_csv(date_str: str, description: str, debit: str = "", credit: str = "") -> bytes:
    """date_str is "YYYY-MM-DD"; the Leumi parser expects "DD/MM/YYYY"."""
    year, month, day = date_str.split("-")
    leumi_date = f"{day}/{month}/{year}"
    return (
        ",,,,,,\n"
        "Bank Leumi - Account Transactions,,,,,\n"
        "Date,Description,Reference Number,Debit,Credit,NIS Balance\n"
        f"{leumi_date},{description},123456,{debit},{credit},1000.00\n"
    ).encode()


async def _category_id(client, group_name: str, category_name: str) -> int:
    categories = (await client.get("/api/categories")).json()
    return next(
        c["id"]
        for g in categories
        if g["name"] == group_name
        for c in g["categories"]
        if c["name"] == category_name
    )


async def _setup_pair(client, db_session, status: str) -> tuple[int, int]:
    """Uploads two same-currency (ILS, the base currency -- no network-
    dependent conversion) expense legs on two different banks so the
    account keys legitimately differ, categorizes both, then inserts an
    InternalTransferMatch row directly with `status` under precise
    control (per the plan: real CSVs for the transactions, a direct DB
    insert for the match row)."""
    today = datetime.utcnow().strftime("%Y-%m-%d")

    await client.post(
        "/api/upload",
        files={"file": ("a.csv", io.BytesIO(_revolut_csv(today, "Move to Leumi", "-40.00")), "text/csv")},
    )
    await client.post(
        "/api/upload",
        files={"file": ("b.csv", io.BytesIO(_leumi_csv(today, "Move from Revolut", debit="40.00")), "text/csv")},
    )

    txns = (await client.get("/api/transactions", params={"page_size": "50"})).json()["transactions"]
    revolut_txn = next(t for t in txns if t["bank"] == "Revolut")
    leumi_txn = next(t for t in txns if t["bank"] == "Leumi")

    groceries_id = await _category_id(client, "Household Expenses", "Groceries")
    await client.patch(f"/api/transactions/{revolut_txn['id']}/category", json={"category_id": groceries_id})
    await client.patch(f"/api/transactions/{leumi_txn['id']}/category", json={"category_id": groceries_id})

    async with db_session() as session:
        session.add(
            InternalTransferMatch(
                outgoing_transaction_id=revolut_txn["id"],
                incoming_transaction_id=leumi_txn["id"],
                confidence="high",
                status=status,
            )
        )
        await session.commit()

    return revolut_txn["id"], leumi_txn["id"]


@pytest.mark.asyncio
async def test_confirmed_match_excludes_both_legs_from_transactions_list(client, db_session):
    revolut_id, leumi_id = await _setup_pair(client, db_session, "confirmed")

    txns = (await client.get("/api/transactions", params={"page_size": "50"})).json()["transactions"]
    ids = {t["id"] for t in txns}
    assert revolut_id not in ids
    assert leumi_id not in ids

    txns_incl = (
        await client.get(
            "/api/transactions", params={"page_size": "50", "include_transfers": "true"}
        )
    ).json()["transactions"]
    ids_incl = {t["id"] for t in txns_incl}
    assert revolut_id in ids_incl
    assert leumi_id in ids_incl


@pytest.mark.asyncio
async def test_confirmed_match_excludes_both_legs_from_dashboard(client, db_session):
    await _setup_pair(client, db_session, "confirmed")

    dashboard = (await client.get("/api/dashboard")).json()
    assert Decimal(dashboard["current_month"]["expenses"]) == Decimal("0")


@pytest.mark.asyncio
async def test_confirmed_match_excludes_both_legs_from_analysis(client, db_session):
    await _setup_pair(client, db_session, "confirmed")

    analysis = (await client.get("/api/analysis")).json()
    assert analysis["daily"] == []
    assert analysis["categories"] == []
    assert analysis["by_currency"] == []
    assert analysis["by_bank"] == []


@pytest.mark.asyncio
async def test_confirmed_match_excludes_both_legs_from_budget_summary(client, db_session):
    now = datetime.utcnow()
    await _setup_pair(client, db_session, "confirmed")

    budget = (await client.get("/api/budget/summary", params={"year": now.year})).json()
    assert budget["total_expense_annual"] == "0"


@pytest.mark.asyncio
async def test_suggested_match_stays_fully_visible_everywhere(client, db_session):
    revolut_id, leumi_id = await _setup_pair(client, db_session, "suggested")

    txns = (await client.get("/api/transactions", params={"page_size": "50"})).json()["transactions"]
    ids = {t["id"] for t in txns}
    assert revolut_id in ids
    assert leumi_id in ids

    dashboard = (await client.get("/api/dashboard")).json()
    assert Decimal(dashboard["current_month"]["expenses"]) == Decimal("80.00")

    analysis = (await client.get("/api/analysis")).json()
    assert len(analysis["daily"]) == 1
    assert Decimal(analysis["daily"][0]["total"]) == Decimal("80.00")


@pytest.mark.asyncio
async def test_rejected_match_stays_fully_visible_everywhere(client, db_session):
    revolut_id, leumi_id = await _setup_pair(client, db_session, "rejected")

    txns = (await client.get("/api/transactions", params={"page_size": "50"})).json()["transactions"]
    ids = {t["id"] for t in txns}
    assert revolut_id in ids
    assert leumi_id in ids

    dashboard = (await client.get("/api/dashboard")).json()
    assert Decimal(dashboard["current_month"]["expenses"]) == Decimal("80.00")

    analysis = (await client.get("/api/analysis")).json()
    assert len(analysis["daily"]) == 1
    assert Decimal(analysis["daily"][0]["total"]) == Decimal("80.00")


@pytest.mark.asyncio
async def test_undo_import_removes_match_rows(client, db_session):
    today = datetime.utcnow().strftime("%Y-%m-%d")

    resp = await client.post(
        "/api/upload",
        files={"file": ("a.csv", io.BytesIO(_revolut_csv(today, "Move to Leumi", "-40.00")), "text/csv")},
    )
    batch_id = resp.json()["batch_id"]

    await client.post(
        "/api/upload",
        files={"file": ("b.csv", io.BytesIO(_leumi_csv(today, "Move from Revolut", debit="40.00")), "text/csv")},
    )

    txns = (await client.get("/api/transactions", params={"page_size": "50"})).json()["transactions"]
    revolut_txn = next(t for t in txns if t["bank"] == "Revolut")
    leumi_txn = next(t for t in txns if t["bank"] == "Leumi")

    async with db_session() as session:
        session.add(
            InternalTransferMatch(
                outgoing_transaction_id=revolut_txn["id"],
                incoming_transaction_id=leumi_txn["id"],
                confidence="high",
                status="confirmed",
            )
        )
        await session.commit()

    await client.delete(f"/api/upload/batches/{batch_id}")

    from sqlalchemy import select

    async with db_session() as session:
        remaining = (await session.execute(select(InternalTransferMatch))).scalars().all()

    assert remaining == []

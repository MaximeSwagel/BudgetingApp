import io
from datetime import datetime

import pytest
from sqlalchemy import select

from app.main import ensure_seed_categories
from app.models import Category, CategoryGroup, InternalTransferMatch


def _revolut_csv(date_str: str, description: str, amount: str, currency: str = "ILS", fee: str = "0") -> bytes:
    return (
        "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
        f"CARD_PAYMENT,Current,{date_str} 10:00:00,{date_str} 10:00:01,{description},{amount},{fee},{currency},COMPLETED,150.00\n"
    ).encode()


def _revolut_csv_no_fee_column(date_str: str, description: str, amount: str, currency: str = "ILS") -> bytes:
    return (
        "Type,Product,Started Date,Completed Date,Description,Amount,Currency,State,Balance\n"
        f"CARD_PAYMENT,Current,{date_str} 10:00:00,{date_str} 10:00:01,{description},{amount},{currency},COMPLETED,150.00\n"
    ).encode()


def _ca_csv(date_str: str, description: str, debit: str = "", credit: str = "") -> bytes:
    """date_str is "YYYY-MM-DD"; the CA parser expects "DD/MM/YYYY"."""
    year, month, day = date_str.split("-")
    ca_date = f"{day}/{month}/{year}"
    return (
        "Date;Libelle;Debit;Credit\n"
        f"{ca_date};{description};{debit};{credit}\n"
    ).encode()


@pytest.mark.asyncio
async def test_fresh_db_seeds_transfer_fees_category(db_session):
    async with db_session() as session:
        result = await session.execute(
            select(Category)
            .join(CategoryGroup)
            .where(
                CategoryGroup.name == "Insurance, Tax & Bank Fees",
                Category.name == "Transfer Fees",
            )
        )
        assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_ensure_seed_categories_is_additive_and_never_reorders_or_deletes(db_session):
    async with db_session() as session:
        group = (
            await session.execute(
                select(CategoryGroup).where(CategoryGroup.name == "Insurance, Tax & Bank Fees")
            )
        ).scalar_one()
        group_id = group.id
        initial_count = len(
            (await session.execute(select(Category).where(Category.group_id == group_id))).scalars().all()
        )

        # A manually inserted extra category the seeding must never touch.
        session.add(Category(name="Custom Extra Category", group_id=group_id, display_order=99))
        await session.commit()

    async with db_session() as session:
        await ensure_seed_categories(session)

    async with db_session() as session:
        await ensure_seed_categories(session)

    async with db_session() as session:
        cats = (await session.execute(select(Category).where(Category.group_id == group_id))).scalars().all()
        names = {c.name for c in cats}
        assert "Custom Extra Category" in names
        assert "Transfer Fees" in names
        # Two calls after the manual insert -- count grew by exactly one
        # (the manual insert), proving idempotency and no deletion/reorder.
        assert len(cats) == initial_count + 1


@pytest.mark.asyncio
async def test_upload_with_fee_creates_principal_and_fee_transaction(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    resp = await client.post(
        "/api/upload",
        files={
            "file": (
                "a.csv",
                io.BytesIO(_revolut_csv(today, "Send to Bob", "-100.00", fee="1.50")),
                "text/csv",
            )
        },
    )
    body = resp.json()
    assert body["imported"] == 1
    assert body["fees_recorded"] == 1

    txns = (await client.get("/api/transactions", params={"page_size": "50"})).json()["transactions"]
    assert len(txns) == 2

    fee_txn = next(t for t in txns if "Transfer fee" in t["description"])
    assert fee_txn["original_amount"] == "-1.50"
    assert fee_txn["category"] == "Transfer Fees"
    assert fee_txn["is_expense"] is True

    principal_txn = next(t for t in txns if t["description"] == "Send to Bob")
    assert principal_txn["original_amount"] == "-100.00"


@pytest.mark.asyncio
async def test_reupload_does_not_duplicate_principal_or_fee_row(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    csv_bytes = _revolut_csv(today, "Send to Bob", "-100.00", fee="1.50")

    await client.post("/api/upload", files={"file": ("a.csv", io.BytesIO(csv_bytes), "text/csv")})
    resp = await client.post("/api/upload", files={"file": ("a.csv", io.BytesIO(csv_bytes), "text/csv")})

    body = resp.json()
    assert body["imported"] == 0
    assert body["fees_recorded"] == 0

    txns = (await client.get("/api/transactions", params={"page_size": "50"})).json()["transactions"]
    assert len(txns) == 2


@pytest.mark.asyncio
async def test_zero_fee_creates_only_principal_transaction(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    await client.post(
        "/api/upload",
        files={"file": ("a.csv", io.BytesIO(_revolut_csv(today, "Coffee", "-10.00", fee="0")), "text/csv")},
    )
    txns = (await client.get("/api/transactions")).json()["transactions"]
    assert len(txns) == 1


@pytest.mark.asyncio
async def test_absent_fee_column_creates_only_principal_transaction(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    await client.post(
        "/api/upload",
        files={"file": ("a.csv", io.BytesIO(_revolut_csv_no_fee_column(today, "Lunch", "-12.00")), "text/csv")},
    )
    txns = (await client.get("/api/transactions")).json()["transactions"]
    assert len(txns) == 1


@pytest.mark.asyncio
async def test_undo_import_removes_fee_row_too(client):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    resp = await client.post(
        "/api/upload",
        files={
            "file": (
                "a.csv",
                io.BytesIO(_revolut_csv(today, "Send to Bob", "-100.00", fee="1.50")),
                "text/csv",
            )
        },
    )
    batch_id = resp.json()["batch_id"]

    await client.delete(f"/api/upload/batches/{batch_id}")

    txns = (await client.get("/api/transactions")).json()["transactions"]
    assert txns == []


@pytest.mark.asyncio
async def test_upload_creates_confirmed_match_without_manual_scan(client, db_session):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    await client.post(
        "/api/upload",
        files={
            "file": (
                "a.csv",
                io.BytesIO(_revolut_csv(today, "To Savings", "-500.00", currency="EUR")),
                "text/csv",
            )
        },
    )
    resp2 = await client.post(
        "/api/upload",
        files={"file": ("b.csv", io.BytesIO(_ca_csv(today, "From Revolut", credit="500,00")), "text/csv")},
    )
    assert resp2.json()["transfers_detected"] == 1

    async with db_session() as session:
        matches = (await session.execute(select(InternalTransferMatch))).scalars().all()

    assert len(matches) == 1
    assert matches[0].status == "confirmed"
    assert matches[0].confidence == "high"

"""Characterization tests for how the upload pipeline handles income rows
(positive amounts). These pin down CURRENT behavior; a case that surfaces a
genuine bug is marked xfail with a clear reason rather than silently rewritten
to match the bug (see SUMMARY for the one bug found here)."""

import io
from datetime import datetime
from decimal import Decimal

import pytest

from app.services import currency as currency_module

REVOLUT_EN_HEADER = "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"


def _revolut_csv(amount: str, currency_code: str = "ILS", description: str = "Test", date_str: str | None = None) -> bytes:
    date_str = date_str or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    row = f"CARD_PAYMENT,Current,{date_str},{date_str},{description},{amount},0,{currency_code},COMPLETED,100.00\n"
    return (REVOLUT_EN_HEADER + row).encode()


@pytest.mark.asyncio
@pytest.mark.xfail(
    reason=(
        "BUG: transactions.py serializes converted_amount with "
        "`str(t.converted_amount) if t.converted_amount else None`. Decimal('0.00') is "
        "falsy in Python (bool(Decimal('0.00')) is False), so a zero-amount converted "
        "row incorrectly serializes as null instead of '0.00'. Fix: compare "
        "`is not None` instead of truthiness."
    ),
    strict=True,
)
async def test_zero_amount_income_imports_and_reports_zero(client):
    files = {"file": ("zero.csv", io.BytesIO(_revolut_csv("0.00")), "text/csv")}
    resp = await client.post("/api/upload", files=files)
    assert resp.status_code == 200
    assert resp.json()["imported"] == 1

    txns = (await client.get("/api/transactions")).json()["transactions"]
    txn = txns[0]
    assert txn["is_expense"] is False
    assert txn["original_amount"] == "0.00"
    assert txn["converted_amount"] == "0.00"


@pytest.mark.asyncio
async def test_sign_drives_income_vs_expense_classification(client):
    """A positive 'refund' row is classified as income (is_expense=False) while a
    genuinely negative row is classified as an expense — classification is driven
    purely by the sign of the amount, documenting current (naive) behavior."""
    refund_csv = _revolut_csv("15.00", description="Refund - Amazon")
    expense_csv = _revolut_csv("-15.00", description="Amazon purchase")

    await client.post("/api/upload", files={"file": ("refund.csv", io.BytesIO(refund_csv), "text/csv")})
    await client.post("/api/upload", files={"file": ("expense.csv", io.BytesIO(expense_csv), "text/csv")})

    txns = (await client.get("/api/transactions", params={"page_size": "50"})).json()["transactions"]
    by_desc = {t["description"]: t for t in txns}

    assert by_desc["Refund - Amazon"]["is_expense"] is False
    assert by_desc["Amazon purchase"]["is_expense"] is True


@pytest.mark.asyncio
async def test_income_in_non_base_currency_converts_without_negation(client, monkeypatch):
    async def fake_rate(from_currency, to_currency, date_str=None):
        return Decimal("4")

    monkeypatch.setattr(currency_module, "get_exchange_rate", fake_rate)

    files = {
        "file": (
            "eur_income.csv",
            io.BytesIO(_revolut_csv("50.00", currency_code="EUR", description="Salary")),
            "text/csv",
        )
    }
    resp = await client.post("/api/upload", files=files)
    assert resp.json()["imported"] == 1

    txns = (await client.get("/api/transactions")).json()["transactions"]
    txn = txns[0]
    assert txn["is_expense"] is False
    assert txn["original_currency"] == "EUR"
    assert txn["converted_amount"] == "200.00"
    # exchange_rate is Numeric(12,6), so the round-tripped value carries full
    # scale precision rather than the bare literal passed to convert_amount.
    assert txn["exchange_rate"] == "4.000000"


@pytest.mark.asyncio
async def test_duplicate_income_is_deduped(client):
    csv_bytes = _revolut_csv("25.00", description="Freelance payment")
    await client.post("/api/upload", files={"file": ("income.csv", io.BytesIO(csv_bytes), "text/csv")})
    resp = await client.post("/api/upload", files={"file": ("income.csv", io.BytesIO(csv_bytes), "text/csv")})

    body = resp.json()
    assert body["imported"] == 0
    assert body["duplicates_skipped"] == 1


@pytest.mark.asyncio
async def test_categorized_income_excluded_from_budget_but_shown_in_dashboard(client):
    """The budget grid (monthly_category_totals) joins Category AND filters
    is_expense == True, so a categorized income row never appears there.
    monthly_totals_since (used by the dashboard) does not join category and
    buckets purely on is_expense, so it counts the row as income."""
    now = datetime.utcnow()
    csv_bytes = _revolut_csv("40.00", description="Consulting income", date_str=now.strftime("%Y-%m-%d %H:%M:%S"))
    await client.post("/api/upload", files={"file": ("income.csv", io.BytesIO(csv_bytes), "text/csv")})

    txns = (await client.get("/api/transactions")).json()["transactions"]
    txn_id = txns[0]["id"]

    categories_resp = await client.get("/api/categories")
    category_id = categories_resp.json()[0]["categories"][0]["id"]
    await client.patch(f"/api/transactions/{txn_id}/category", json={"category_id": category_id})

    budget_resp = await client.get("/api/budget/summary", params={"year": now.year})
    assert budget_resp.json()["total_expense_annual"] == "0"

    dashboard_resp = await client.get("/api/dashboard")
    assert dashboard_resp.json()["current_month"]["income"] == "40.00"


@pytest.mark.asyncio
async def test_uncategorized_income_counts_in_dashboard_not_budget(client):
    """Without an OpenAI/Anthropic key configured, imported rows stay
    category_id=None. Dashboard still counts income (no category join);
    the category-joined budget grid never surfaces it (both because it is
    income, and because it has no category)."""
    now = datetime.utcnow()
    csv_bytes = _revolut_csv("60.00", description="Cash gift", date_str=now.strftime("%Y-%m-%d %H:%M:%S"))
    await client.post("/api/upload", files={"file": ("gift.csv", io.BytesIO(csv_bytes), "text/csv")})

    txns = (await client.get("/api/transactions")).json()["transactions"]
    assert txns[0]["category_id"] is None

    dashboard_resp = await client.get("/api/dashboard")
    assert dashboard_resp.json()["current_month"]["income"] == "60.00"

    budget_resp = await client.get("/api/budget/summary", params={"year": now.year})
    assert budget_resp.json()["total_expense_annual"] == "0"


@pytest.mark.asyncio
async def test_income_conversion_rounds_half_even(client, monkeypatch):
    """convert_amount quantizes to 2dp with Decimal's default ROUND_HALF_EVEN;
    income rows go through the exact same convert_amount() call as expenses, so
    they round identically -- 1.00 EUR * 0.125 = 0.125 -> '0.12' (2 is even)."""

    async def fake_rate(from_currency, to_currency, date_str=None):
        return Decimal("0.125")

    monkeypatch.setattr(currency_module, "get_exchange_rate", fake_rate)

    files = {
        "file": (
            "round.csv",
            io.BytesIO(_revolut_csv("1.00", currency_code="EUR", description="Rounding test")),
            "text/csv",
        )
    }
    await client.post("/api/upload", files=files)

    txns = (await client.get("/api/transactions")).json()["transactions"]
    assert txns[0]["converted_amount"] == "0.12"

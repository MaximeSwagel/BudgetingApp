import io

import pytest
from sqlalchemy import select

from app.models import CategoryCorrection, CategoryGroupTarget

JAN_EXPENSE_CSV = (
    "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
    "CARD_PAYMENT,Current,2026-01-05 10:00:00,2026-01-05 10:00:01,Tesco,-20.00,0,ILS,COMPLETED,150.00\n"
)


async def _categorize_all(client, category_id: int):
    txns = (await client.get("/api/transactions", params={"uncategorized": "true", "page_size": "200"})).json()
    for t in txns["transactions"]:
        await client.patch(f"/api/transactions/{t['id']}/category", json={"category_id": category_id})


@pytest.mark.asyncio
async def test_create_group_and_subcategory(client):
    group_resp = await client.post("/api/categories/groups", json={"name": "New Primary"})
    assert group_resp.status_code == 200
    group = group_resp.json()
    assert group["name"] == "New Primary"

    cat_resp = await client.post("/api/categories", json={"name": "New Sub", "group_id": group["id"]})
    assert cat_resp.status_code == 200
    cat = cat_resp.json()
    assert cat["name"] == "New Sub"
    assert cat["group_id"] == group["id"]

    categories = (await client.get("/api/categories")).json()
    match = next(g for g in categories if g["id"] == group["id"])
    assert any(c["name"] == "New Sub" for c in match["categories"])


@pytest.mark.asyncio
async def test_duplicate_group_name_returns_409(client):
    resp = await client.post("/api/categories/groups", json={"name": "Home Expenses"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_duplicate_subcategory_in_group_returns_409(client):
    categories = (await client.get("/api/categories")).json()
    home = next(g for g in categories if g["name"] == "Home Expenses")
    existing_name = home["categories"][0]["name"]  # "Rent"

    dup_resp = await client.post(
        "/api/categories", json={"name": existing_name, "group_id": home["id"]}
    )
    assert dup_resp.status_code == 409

    other_group = next(g for g in categories if g["name"] != "Home Expenses")
    ok_resp = await client.post(
        "/api/categories", json={"name": existing_name, "group_id": other_group["id"]}
    )
    assert ok_resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_empty_subcategory(client):
    categories = (await client.get("/api/categories")).json()
    group_id = categories[0]["id"]
    cat = (await client.post("/api/categories", json={"name": "Throwaway", "group_id": group_id})).json()

    del_resp = await client.delete(f"/api/categories/{cat['id']}")
    assert del_resp.status_code == 200

    categories_after = (await client.get("/api/categories")).json()
    names = [c["name"] for g in categories_after for c in g["categories"]]
    assert "Throwaway" not in names


@pytest.mark.asyncio
async def test_delete_subcategory_with_transactions_blocked_409(client):
    await client.post("/api/upload", files={"file": ("a.csv", io.BytesIO(JAN_EXPENSE_CSV.encode()), "text/csv")})
    categories = (await client.get("/api/categories")).json()
    cat_id = categories[0]["categories"][0]["id"]
    await _categorize_all(client, cat_id)

    del_resp = await client.delete(f"/api/categories/{cat_id}")
    assert del_resp.status_code == 409

    categories_after = (await client.get("/api/categories")).json()
    ids = [c["id"] for g in categories_after for c in g["categories"]]
    assert cat_id in ids


@pytest.mark.asyncio
async def test_delete_subcategory_cleans_corrections(client, db_session):
    categories = (await client.get("/api/categories")).json()
    group_id = categories[0]["id"]

    cat = (await client.post("/api/categories", json={"name": "Temp Sub", "group_id": group_id})).json()
    cat_id = cat["id"]

    async with db_session() as session:
        session.add(
            CategoryCorrection(
                merchant_key="temp merchant",
                description_sample="Temp Merchant",
                category_id=cat_id,
                original_category_id=cat_id,
            )
        )
        await session.commit()

    del_resp = await client.delete(f"/api/categories/{cat_id}")
    assert del_resp.status_code == 200

    categories_after = (await client.get("/api/categories")).json()
    names = [c["name"] for g in categories_after for c in g["categories"]]
    assert "Temp Sub" not in names

    summary = (await client.get("/api/budget/summary", params={"year": 2026})).json()
    all_cat_ids = [c["category_id"] for g in summary["groups"] for c in g["categories"]]
    assert cat_id not in all_cat_ids

    async with db_session() as session:
        result = await session.execute(
            select(CategoryCorrection).where(CategoryCorrection.merchant_key == "temp merchant")
        )
        correction = result.scalar_one()
        assert correction.category_id is None
        assert correction.original_category_id is None


@pytest.mark.asyncio
async def test_delete_group_with_subcategories_blocked_409(client):
    categories = (await client.get("/api/categories")).json()
    home = next(g for g in categories if g["name"] == "Home Expenses")

    del_resp = await client.delete(f"/api/categories/groups/{home['id']}")
    assert del_resp.status_code == 409

    categories_after = (await client.get("/api/categories")).json()
    assert any(g["name"] == "Home Expenses" for g in categories_after)


@pytest.mark.asyncio
async def test_delete_empty_group(client):
    group = (await client.post("/api/categories/groups", json={"name": "Empty Group"})).json()

    del_resp = await client.delete(f"/api/categories/groups/{group['id']}")
    assert del_resp.status_code == 200

    categories_after = (await client.get("/api/categories")).json()
    assert not any(g["name"] == "Empty Group" for g in categories_after)


@pytest.mark.asyncio
async def test_delete_group_cleans_group_targets(client, db_session):
    group = (await client.post("/api/categories/groups", json={"name": "Temp Group"})).json()
    group_id = group["id"]

    target_resp = await client.post(
        "/api/budget/group-targets", json={"group_id": group_id, "amount": "100.00"}
    )
    assert target_resp.json()["ok"] is True

    del_resp = await client.delete(f"/api/categories/groups/{group_id}")
    assert del_resp.status_code == 200

    async with db_session() as session:
        result = await session.execute(
            select(CategoryGroupTarget).where(CategoryGroupTarget.group_id == group_id)
        )
        assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_delete_missing_category_and_group_404(client):
    cat_resp = await client.delete("/api/categories/999999")
    assert cat_resp.status_code == 404

    group_resp = await client.delete("/api/categories/groups/999999")
    assert group_resp.status_code == 404


@pytest.mark.asyncio
async def test_budget_summary_includes_group_id(client):
    categories = (await client.get("/api/categories")).json()
    id_by_name = {g["name"]: g["id"] for g in categories}

    summary = (await client.get("/api/budget/summary", params={"year": 2026})).json()
    for g in summary["groups"]:
        assert isinstance(g["group_id"], int)
        assert g["group_id"] == id_by_name[g["group"]]
        assert "categories" in g
        assert "monthly_totals" in g
        assert "annual_total" in g
    assert "total_expense_monthly" in summary
    assert "total_expense_annual" in summary

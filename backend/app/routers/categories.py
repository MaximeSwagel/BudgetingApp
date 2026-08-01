from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Category, CategoryGroup
from app.repositories import (
    BudgetTargetRepository,
    CategoryCorrectionRepository,
    CategoryGroupRepository,
    CategoryRepository,
    TransactionRepository,
)

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("")
async def list_categories(db: AsyncSession = Depends(get_db)):
    repo = CategoryGroupRepository(db)
    groups = await repo.list_with_categories()

    return [
        {
            "id": g.id,
            "name": g.name,
            "categories": [
                {"id": c.id, "name": c.name}
                for c in sorted(g.categories, key=lambda x: x.display_order)
            ],
        }
        for g in groups
    ]


@router.post("/groups")
async def create_group(body: dict, db: AsyncSession = Depends(get_db)):
    repo = CategoryGroupRepository(db)

    existing = await repo.get_by_name(body["name"])
    if existing:
        raise HTTPException(status_code=409, detail=f"A primary category named '{body['name']}' already exists")

    group = repo.add(CategoryGroup(name=body["name"], display_order=body.get("display_order", 0)))
    await repo.commit()
    await repo.refresh(group)
    return {"id": group.id, "name": group.name}


@router.post("")
async def create_category(body: dict, db: AsyncSession = Depends(get_db)):
    repo = CategoryRepository(db)

    existing = await repo.get_by_name_in_group(body["name"], body["group_id"])
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A subcategory named '{body['name']}' already exists in this primary category",
        )

    cat = repo.add(
        Category(
            name=body["name"],
            group_id=body["group_id"],
            display_order=body.get("display_order", 0),
        )
    )
    await repo.commit()
    await repo.refresh(cat)
    return {"id": cat.id, "name": cat.name, "group_id": cat.group_id}


@router.put("/{category_id}")
async def update_category(category_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    repo = CategoryRepository(db)
    cat = await repo.get(category_id)
    if not cat:
        return {"error": "Category not found"}

    if "name" in body:
        cat.name = body["name"]
    if "group_id" in body:
        cat.group_id = body["group_id"]
    await repo.commit()
    return {"id": cat.id, "name": cat.name, "group_id": cat.group_id}


@router.delete("/groups/{group_id}")
async def delete_group(group_id: int, db: AsyncSession = Depends(get_db)):
    """D-03: block-unless-empty. The user removes subcategories first (each
    of which runs the transaction check below), so this makes the model's
    cascade='all, delete-orphan' harmless -- there's nothing left to cascade
    by the time a group is actually deletable."""
    repo = CategoryGroupRepository(db)
    group = await repo.get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Primary category not found")

    category_repo = CategoryRepository(db)
    remaining = await category_repo.count_in_group(group_id)
    if remaining > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete '{group.name}': it still has {remaining} subcategory(ies). Remove those first.",
        )

    await repo.remove(group)
    await repo.commit()
    return {"ok": True}


@router.delete("/{category_id}")
async def delete_category(category_id: int, db: AsyncSession = Depends(get_db)):
    """D-02: safe-block-on-real-data. Blocks with 409 if any transaction
    still references this category (never silently orphan imported
    financial rows -- the user must reassign those first). If there are no
    transactions, proactively cleans derived/metadata references (budget
    targets, correction FKs) so Postgres never sees a dangling FK, then
    deletes the category itself."""
    repo = CategoryRepository(db)
    category = await repo.get(category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Subcategory not found")

    txn_repo = TransactionRepository(db)
    txn_count = await txn_repo.count_by_category(category_id)
    if txn_count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot delete '{category.name}': {txn_count} transaction(s) are assigned to it. "
                "Reassign them first."
            ),
        )

    await BudgetTargetRepository(db).delete_by_category(category_id)
    await CategoryCorrectionRepository(db).clear_category(category_id)
    await repo.remove(category)
    await repo.commit()
    return {"ok": True}

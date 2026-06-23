from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import Category, CategoryGroup

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("")
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CategoryGroup)
        .options(joinedload(CategoryGroup.categories))
        .order_by(CategoryGroup.display_order)
    )
    groups = result.scalars().unique().all()

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
    group = CategoryGroup(name=body["name"], display_order=body.get("display_order", 0))
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return {"id": group.id, "name": group.name}


@router.post("")
async def create_category(body: dict, db: AsyncSession = Depends(get_db)):
    cat = Category(
        name=body["name"],
        group_id=body["group_id"],
        display_order=body.get("display_order", 0),
    )
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return {"id": cat.id, "name": cat.name, "group_id": cat.group_id}


@router.put("/{category_id}")
async def update_category(category_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).where(Category.id == category_id))
    cat = result.scalar_one_or_none()
    if not cat:
        return {"error": "Category not found"}

    if "name" in body:
        cat.name = body["name"]
    if "group_id" in body:
        cat.group_id = body["group_id"]
    await db.commit()
    return {"id": cat.id, "name": cat.name, "group_id": cat.group_id}

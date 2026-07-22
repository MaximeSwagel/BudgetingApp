from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Category, CategoryGroup
from app.repositories import CategoryGroupRepository, CategoryRepository

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
    group = repo.add(CategoryGroup(name=body["name"], display_order=body.get("display_order", 0)))
    await repo.commit()
    await repo.refresh(group)
    return {"id": group.id, "name": group.name}


@router.post("")
async def create_category(body: dict, db: AsyncSession = Depends(get_db)):
    repo = CategoryRepository(db)
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

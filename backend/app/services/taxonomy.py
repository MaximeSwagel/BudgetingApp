from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.repositories.categories import CategoryGroupRepository


async def load_category_hierarchy(session: AsyncSession | None = None) -> dict[str, list[str]]:
    """Group name -> subcategory names, in display order. Read on every call so edits apply at once."""
    if session is None:
        async with async_session() as own:
            return await load_category_hierarchy(own)
    groups = await CategoryGroupRepository(session).list_with_categories()
    return {
        group.name: [c.name for c in sorted(group.categories, key=lambda c: (c.display_order, c.id))]
        for group in sorted(groups, key=lambda g: (g.display_order, g.id))
    }

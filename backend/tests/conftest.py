import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import SEED_CATEGORIES, app
from app.models import Base, Category, CategoryGroup


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        for order, (group_name, cats) in enumerate(SEED_CATEGORIES.items()):
            group = CategoryGroup(name=group_name, display_order=order)
            session.add(group)
            await session.flush()
            for cat_order, cat_name in enumerate(cats):
                session.add(Category(name=cat_name, group_id=group.id, display_order=cat_order))
        await session.commit()

    yield session_factory

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        async with db_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import CategoryGroup, CategoryGroupTarget
from app.repositories import CategoryGroupTargetRepository


async def _make_group(session, name: str) -> int:
    group = CategoryGroup(name=name, display_order=0)
    session.add(group)
    await session.flush()
    await session.commit()
    return group.id


@pytest.mark.asyncio
async def test_upsert_inserts(db_session):
    async with db_session() as session:
        group_id = await _make_group(session, "G1")
        repo = CategoryGroupTargetRepository(session)
        await repo.upsert_for_month(
            group_id=group_id, amount=Decimal("500"), effective_month=date(2026, 1, 1)
        )
        await session.commit()

        result = await session.execute(
            select(CategoryGroupTarget).where(
                CategoryGroupTarget.group_id == group_id,
                CategoryGroupTarget.effective_month == date(2026, 1, 1),
            )
        )
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].amount == Decimal("500")


@pytest.mark.asyncio
async def test_upsert_within_same_month_updates_in_place(db_session):
    async with db_session() as session:
        group_id = await _make_group(session, "G1")
        repo = CategoryGroupTargetRepository(session)
        await repo.upsert_for_month(
            group_id=group_id, amount=Decimal("500"), effective_month=date(2026, 1, 1)
        )
        await session.commit()
        await repo.upsert_for_month(
            group_id=group_id, amount=Decimal("800"), effective_month=date(2026, 1, 1)
        )
        await session.commit()

        result = await session.execute(
            select(CategoryGroupTarget).where(CategoryGroupTarget.group_id == group_id)
        )
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].amount == Decimal("800")


@pytest.mark.asyncio
async def test_single_target_applies_to_every_month(db_session):
    async with db_session() as session:
        group_id = await _make_group(session, "G1")
        repo = CategoryGroupTargetRepository(session)
        await repo.upsert_for_month(
            group_id=group_id, amount=Decimal("500"), effective_month=date(2026, 1, 1)
        )
        await session.commit()

        targets = await repo.current_targets_by_month()
        for month in range(1, 13):
            assert targets[group_id][month] == Decimal("500")


@pytest.mark.asyncio
async def test_latest_row_wins_for_every_month(db_session):
    async with db_session() as session:
        group_id = await _make_group(session, "G1")
        repo = CategoryGroupTargetRepository(session)
        await repo.upsert_for_month(
            group_id=group_id, amount=Decimal("500"), effective_month=date(2026, 1, 1)
        )
        await repo.upsert_for_month(
            group_id=group_id, amount=Decimal("800"), effective_month=date(2026, 6, 1)
        )
        await session.commit()

        targets = await repo.current_targets_by_month()
        for month in range(1, 13):
            assert targets[group_id][month] == Decimal("800")


@pytest.mark.asyncio
async def test_clearing_removes_target_from_every_month(db_session):
    async with db_session() as session:
        group_id = await _make_group(session, "G1")
        repo = CategoryGroupTargetRepository(session)
        await repo.upsert_for_month(
            group_id=group_id, amount=Decimal("500"), effective_month=date(2026, 1, 1)
        )
        await repo.upsert_for_month(
            group_id=group_id, amount=Decimal("800"), effective_month=date(2026, 6, 1)
        )
        await repo.upsert_for_month(
            group_id=group_id, amount=None, effective_month=date(2026, 9, 1)
        )
        await session.commit()

        targets = await repo.current_targets_by_month()
        for month in range(1, 13):
            assert targets[group_id][month] is None

        current = await repo.current_targets()
        assert current[group_id] is None


@pytest.mark.asyncio
async def test_no_date_gating_future_row_wins(db_session):
    async with db_session() as session:
        group_id = await _make_group(session, "G1")
        repo = CategoryGroupTargetRepository(session)
        await repo.upsert_for_month(
            group_id=group_id, amount=Decimal("500"), effective_month=date(2026, 1, 1)
        )
        await repo.upsert_for_month(
            group_id=group_id, amount=Decimal("900"), effective_month=date(2030, 1, 1)
        )
        await session.commit()

        targets = await repo.current_targets_by_month()
        for month in range(1, 13):
            assert targets[group_id][month] == Decimal("900")


@pytest.mark.asyncio
async def test_group_isolation(db_session):
    async with db_session() as session:
        group1 = await _make_group(session, "G1")
        group2 = await _make_group(session, "G2")
        group3 = await _make_group(session, "G3")
        repo = CategoryGroupTargetRepository(session)
        await repo.upsert_for_month(
            group_id=group1, amount=Decimal("100"), effective_month=date(2026, 1, 1)
        )
        await repo.upsert_for_month(
            group_id=group2, amount=Decimal("999"), effective_month=date(2026, 1, 1)
        )
        await session.commit()

        targets = await repo.current_targets_by_month()
        for month in range(1, 13):
            assert targets[group1][month] == Decimal("100")
            assert targets[group2][month] == Decimal("999")
        # group3 has no rows at all -- absent from the map
        assert group3 not in targets


@pytest.mark.asyncio
async def test_current_targets_and_delete_by_group(db_session):
    async with db_session() as session:
        group1 = await _make_group(session, "G1")
        group2 = await _make_group(session, "G2")
        repo = CategoryGroupTargetRepository(session)
        await repo.upsert_for_month(
            group_id=group1, amount=Decimal("500"), effective_month=date(2026, 1, 1)
        )
        await repo.upsert_for_month(
            group_id=group1, amount=Decimal("800"), effective_month=date(2026, 6, 1)
        )
        await repo.upsert_for_month(
            group_id=group2, amount=Decimal("300"), effective_month=date(2026, 1, 1)
        )
        await session.commit()

        current = await repo.current_targets()
        assert current[group1] == Decimal("800")
        assert current[group2] == Decimal("300")

        await repo.delete_by_group(group1)
        await session.commit()

        result = await session.execute(
            select(CategoryGroupTarget).where(CategoryGroupTarget.group_id == group1)
        )
        assert result.scalars().all() == []

        result2 = await session.execute(
            select(CategoryGroupTarget).where(CategoryGroupTarget.group_id == group2)
        )
        assert len(result2.scalars().all()) == 1

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import delete

from app.main import SEED_CATEGORIES
from app.models import Category, CategoryGroup
from app.services import classifier, taxonomy
from app.services.agents import jev as jev_mod
from app.services.agents import llm as llm_mod
from app.services.agents.base import UNCATEGORIZED
from app.services.agents.llm import OpenAiAgent
from app.services.taxonomy import load_category_hierarchy


def seed():
    return {g: list(c) for g, c in SEED_CATEGORIES.items()}


async def test_seeded_hierarchy_in_seed_order(db_taxonomy):
    async with db_taxonomy() as s:
        loaded = await load_category_hierarchy(s)
    assert loaded == seed()
    assert list(loaded) == list(SEED_CATEGORIES)


async def test_uses_app_session_when_none_given(db_taxonomy):
    assert await load_category_hierarchy() == seed()


async def test_display_order_then_id(db_taxonomy):
    async with db_taxonomy() as s:
        s.add(CategoryGroup(name="First", display_order=-1))
        s.add(CategoryGroup(name="Last", display_order=0))
        group = (await s.execute(CategoryGroup.__table__.select().where(CategoryGroup.name == "Home Expenses"))).one()
        s.add(Category(name="Early", group_id=group.id, display_order=-5))
        await s.commit()
    loaded = await load_category_hierarchy()
    names = list(loaded)
    assert names[0] == "First"
    assert names.index("Last") > names.index("Home Expenses")
    assert loaded["Home Expenses"][0] == "Early"


async def test_empty_db_gives_empty_dict(db_taxonomy):
    async with db_taxonomy() as s:
        await s.execute(delete(Category))
        await s.execute(delete(CategoryGroup))
        await s.commit()
    assert await load_category_hierarchy() == {}


async def test_added_and_renamed_categories_reach_prompt_and_jev(client, db_taxonomy):
    groups = (await client.get("/api/categories")).json()
    household = next(g for g in groups if g["name"] == "Household Expenses")
    grocery = next(c for c in household["categories"] if c["name"] == "Groceries")
    r = await client.post("/api/categories", json={"name": "Pet Food", "group_id": household["id"]})
    assert r.status_code in (200, 201)
    r = await client.put(f"/api/categories/{grocery['id']}", json={"name": "Supermarket"})
    assert r.status_code == 200

    loaded = await load_category_hierarchy()
    batch = [{"description": "x", "original_amount": "1", "original_currency": "ILS", "bank": "B"}]
    prompt = llm_mod._build_prompt(batch, loaded)
    criteria = jev_mod.build_options(loaded).group_criteria
    text = " ".join(criteria.values())
    for blob in (prompt, text):
        assert "Pet Food" in blob and "Supermarket" in blob and "Groceries" not in blob


async def test_classifier_sees_category_added_between_calls(db_taxonomy, monkeypatch):
    seen = []

    class Agent:
        provider, label, env_var, model = "stub", "Stub", "K", "m"
        last_run_stats = {}

        def is_configured(self):
            return True

        async def classify(self, transactions, categories):
            seen.append(categories)
            return [dict(UNCATEGORIZED) for _ in transactions]

    monkeypatch.setattr(classifier, "get_active_agent", lambda: Agent())
    txns = [{"description": "x", "original_amount": "1", "original_currency": "ILS", "bank": "B"}]
    await classifier.categorize_transactions(txns)
    async with db_taxonomy() as s:
        group = (await s.execute(CategoryGroup.__table__.select().where(CategoryGroup.name == "Health Care"))).one()
        s.add(Category(name="Optician", group_id=group.id, display_order=99))
        await s.commit()
    await classifier.categorize_transactions(txns)
    assert "Optician" not in seen[0]["Health Care"]
    assert seen[1]["Health Care"][-1] == "Optician"

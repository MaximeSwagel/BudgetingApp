import pytest

from app.config import settings
from app.services.categorizer import categorize_transactions

TXNS = [
    {"description": "Tesco", "original_amount": "20.00", "original_currency": "ILS", "bank": "Revolut"},
    {"description": "Weird Merchant", "original_amount": "8.50", "original_currency": "ILS", "bank": "Revolut"},
]


@pytest.mark.asyncio
async def test_categorize_anthropic_no_key_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    results = await categorize_transactions(TXNS)

    assert len(results) == len(TXNS)
    assert all(r == {"general_category": "Uncategorized", "precise_category": "Uncategorized"} for r in results)


@pytest.mark.asyncio
async def test_categorize_openai_no_key_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "")

    results = await categorize_transactions(TXNS)

    assert len(results) == len(TXNS)
    assert all(r == {"general_category": "Uncategorized", "precise_category": "Uncategorized"} for r in results)

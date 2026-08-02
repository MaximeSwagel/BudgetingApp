import pytest

from app.config import settings


@pytest.mark.asyncio
async def test_get_ai_settings_shape(client):
    resp = await client.get("/api/settings/ai")
    body = resp.json()

    assert "ai_provider" in body
    assert "openai_model" in body
    assert "anthropic_model" in body
    assert "openai_key_configured" in body
    assert "anthropic_key_configured" in body
    assert "openai_api_key" not in body
    assert "anthropic_api_key" not in body


@pytest.mark.asyncio
async def test_get_ai_models_catalog(client):
    resp = await client.get("/api/settings/ai/models")
    body = resp.json()

    assert "openai" in body["providers"]
    assert "anthropic" in body["providers"]
    for provider_models in body["providers"].values():
        assert len(provider_models) > 0
        for model in provider_models:
            assert "est_cost_per_1000_txns" in model
            assert model["est_cost_per_1000_txns"] >= 0


@pytest.mark.asyncio
async def test_put_ai_settings_round_trip(client, monkeypatch):
    # Snapshot the mutated fields via monkeypatch so the global config
    # singleton is restored at teardown and doesn't leak into other tests.
    monkeypatch.setattr(settings, "ai_provider", settings.ai_provider)
    monkeypatch.setattr(settings, "openai_model", settings.openai_model)
    monkeypatch.setattr(settings, "anthropic_model", settings.anthropic_model)

    resp = await client.put(
        "/api/settings/ai",
        json={"ai_provider": "anthropic", "openai_model": "gpt-4o", "anthropic_model": "claude-opus-4-8"},
    )
    assert resp.status_code == 200

    body = (await client.get("/api/settings/ai")).json()
    assert body["ai_provider"] == "anthropic"
    assert body["openai_model"] == "gpt-4o"
    assert body["anthropic_model"] == "claude-opus-4-8"


@pytest.mark.asyncio
async def test_put_ai_settings_rejects_invalid_provider(client):
    resp = await client.put("/api/settings/ai", json={"ai_provider": "not-a-real-provider"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_recurring_settings_defaults_to_config(client):
    resp = await client.get("/api/settings/recurring")
    assert resp.status_code == 200
    assert resp.json()["recurring_large_threshold"] == str(settings.recurring_large_threshold)


@pytest.mark.asyncio
async def test_put_recurring_settings_round_trip(client):
    resp = await client.put("/api/settings/recurring", json={"recurring_large_threshold": "250"})
    assert resp.status_code == 200
    assert resp.json()["recurring_large_threshold"] == "250"

    body = (await client.get("/api/settings/recurring")).json()
    assert body["recurring_large_threshold"] == "250"


@pytest.mark.asyncio
async def test_put_recurring_settings_rejects_non_numeric(client):
    resp = await client.put("/api/settings/recurring", json={"recurring_large_threshold": "lots"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_put_recurring_settings_rejects_non_positive(client):
    resp = await client.put("/api/settings/recurring", json={"recurring_large_threshold": "0"})
    assert resp.status_code == 400

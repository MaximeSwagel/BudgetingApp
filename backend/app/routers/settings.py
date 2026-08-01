from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.repositories import UserSettingsRepository

router = APIRouter(prefix="/api/settings", tags=["settings"])

AI_SETTING_KEYS = ("ai_provider", "openai_model", "anthropic_model")
VALID_PROVIDERS = ("openai", "anthropic")

# Rough token-usage assumptions for a single transaction categorization call
# at the categorizer's batch size of 30 — used only to produce an indicative
# cost estimate on the Settings page, not a billing-accurate figure.
EST_INPUT_TOKENS_PER_TXN = 150
EST_OUTPUT_TOKENS_PER_TXN = 30

# Pricing is hardcoded and approximate ($ per 1M tokens); there is no live
# pricing API, so these numbers may drift from the providers' current rates.
MODEL_CATALOG = {
    "openai": [
        {"id": "gpt-4o-mini", "label": "GPT-4o mini", "input_per_1m": 0.15, "output_per_1m": 0.60},
        {"id": "gpt-4o", "label": "GPT-4o", "input_per_1m": 2.50, "output_per_1m": 10.00},
    ],
    "anthropic": [
        {"id": "claude-haiku-4-5", "label": "Claude Haiku 4.5", "input_per_1m": 1.00, "output_per_1m": 5.00},
        {
            "id": "claude-sonnet-5",
            "label": "Claude Sonnet 5 (intro pricing through 2026-08-31)",
            "input_per_1m": 2.00,
            "output_per_1m": 10.00,
        },
        {"id": "claude-opus-4-8", "label": "Claude Opus 4.8", "input_per_1m": 5.00, "output_per_1m": 25.00},
    ],
}


def _est_cost_per_1000_txns(input_per_1m: float, output_per_1m: float) -> float:
    input_cost = 1000 * (EST_INPUT_TOKENS_PER_TXN / 1_000_000) * input_per_1m
    output_cost = 1000 * (EST_OUTPUT_TOKENS_PER_TXN / 1_000_000) * output_per_1m
    return round(input_cost + output_cost, 4)


def apply_ai_settings_to_config(values: dict) -> None:
    """Push persisted/updated AI settings into the running config singleton
    so the categorizer picks them up immediately, without a restart."""
    for key in AI_SETTING_KEYS:
        if key in values:
            setattr(settings, key, values[key])


def _current_ai_settings() -> dict:
    return {
        "ai_provider": settings.ai_provider,
        "openai_model": settings.openai_model,
        "anthropic_model": settings.anthropic_model,
        "openai_key_configured": bool(settings.openai_api_key),
        "anthropic_key_configured": bool(settings.anthropic_api_key),
    }


@router.get("/ai")
async def get_ai_settings(db: AsyncSession = Depends(get_db)):
    return _current_ai_settings()


@router.put("/ai")
async def update_ai_settings(body: dict, db: AsyncSession = Depends(get_db)):
    provider = body.get("ai_provider", settings.ai_provider)
    if provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"ai_provider must be one of {VALID_PROVIDERS}")

    repo = UserSettingsRepository(db)
    for key in AI_SETTING_KEYS:
        if key in body:
            await repo.upsert(key, str(body[key]))
    await repo.commit()

    apply_ai_settings_to_config(body)
    return _current_ai_settings()


@router.get("/ai/models")
async def get_ai_models():
    providers = {
        provider: [
            {
                **model,
                "est_cost_per_1000_txns": _est_cost_per_1000_txns(model["input_per_1m"], model["output_per_1m"]),
            }
            for model in models
        ]
        for provider, models in MODEL_CATALOG.items()
    }
    return {
        "providers": providers,
        "token_estimate_assumptions": {
            "input_tokens_per_txn": EST_INPUT_TOKENS_PER_TXN,
            "output_tokens_per_txn": EST_OUTPUT_TOKENS_PER_TXN,
            "note": "Approximate, hardcoded assumptions — actual usage varies by transaction description length.",
        },
    }

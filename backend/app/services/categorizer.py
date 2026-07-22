import json
import logging

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

CATEGORY_HIERARCHY = {
    "Home Expenses": ["Rent", "Utilities: Gas, Electric, Water", "Internet, TV"],
    "Household Expenses": [
        "Groceries", "ATM Withdrawals", "Clothing", "Furniture & Equipment",
        "Laundry & Dry Cleaning", "Cell Phone",
    ],
    "Insurance, Tax & Bank Fees": [
        "Renters Insurance", "Other Insurance", "Income Tax", "Bank Fees",
    ],
    "Health Care": ["Health Insurance", "Dental Insurance", "Doctor & Dentist"],
    "Discretionary": [
        "Restaurants & Coffee Shops", "Classes", "Subscriptions",
        "Concerts & Shows", "Gym/Sports", "Travel/Vacation",
    ],
}

ALL_CATEGORIES_TEXT = "\n".join(
    f"- {group}: {', '.join(cats)}"
    for group, cats in CATEGORY_HIERARCHY.items()
)

# Structured-output schema for the Anthropic branch — Claude's structured
# outputs require a top-level JSON object, so the array of results is wrapped
# under a "results" key (unlike the OpenAI branch, which accepts a bare array
# inside a json_object response).
ANTHROPIC_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "general_category": {"type": "string"},
                    "precise_category": {"type": "string"},
                },
                "required": ["general_category", "precise_category"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}

UNCATEGORIZED = {"general_category": "Uncategorized", "precise_category": "Uncategorized"}


def _build_prompt(batch: list[dict]) -> str:
    """Build the identical categorization prompt used by both provider branches."""
    descriptions = [
        f"{idx+1}. {t['description']} | {t['original_amount']} {t['original_currency']} | {t['bank']}"
        for idx, t in enumerate(batch)
    ]

    return f"""Categorize each transaction into the budget hierarchy below.

Categories:
{ALL_CATEGORIES_TEXT}

For each transaction, return the General Category (group name) and Precise Description (subcategory name).
Use EXACTLY the category names listed above.

Transactions:
{chr(10).join(descriptions)}

Return a JSON array with objects having "general_category" and "precise_category" fields.
Return ONLY the JSON array, no other text."""


async def resolve_category_id(cat_data: dict, group_repo, category_repo) -> int | None:
    """Map a categorizer result to a category id, or None when it produced
    nothing usable (the transaction then stays honestly uncategorized).
    Shared by CSV upload and the bulk auto-categorize endpoint."""
    general = cat_data.get("general_category", "Uncategorized")
    precise = cat_data.get("precise_category", "Uncategorized")

    if general == "Uncategorized":
        return None
    group = await group_repo.get_by_name(general)
    if not group:
        return None
    cat = await category_repo.get_by_name_in_group(precise, group.id)
    if not cat:
        cat = await category_repo.first_in_group(group.id)
    return cat.id if cat else None


async def _categorize_openai(transactions: list[dict]) -> list[dict]:
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    batch_size = 30
    results = []

    for i in range(0, len(transactions), batch_size):
        batch = transactions[i:i + batch_size]
        prompt = _build_prompt(batch)

        try:
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)
            categories = parsed.get("categories", parsed.get("results", []))
            if isinstance(parsed, list):
                categories = parsed
            elif isinstance(parsed, dict) and not categories:
                for v in parsed.values():
                    if isinstance(v, list):
                        categories = v
                        break

            while len(categories) < len(batch):
                categories.append(dict(UNCATEGORIZED))
            results.extend(categories[:len(batch)])
        except Exception as e:
            logger.error(f"OpenAI categorization failed: {e}")
            results.extend([dict(UNCATEGORIZED)] * len(batch))

    return results


async def _categorize_anthropic(transactions: list[dict]) -> list[dict]:
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    batch_size = 30
    results = []

    for i in range(0, len(transactions), batch_size):
        batch = transactions[i:i + batch_size]
        prompt = _build_prompt(batch)

        try:
            response = await client.messages.create(
                model=settings.anthropic_model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
                output_config={"format": {"type": "json_schema", "schema": ANTHROPIC_RESULT_SCHEMA}},
            )
            text = next((block.text for block in response.content if block.type == "text"), "{}")
            parsed = json.loads(text)
            categories = parsed.get("results", [])

            while len(categories) < len(batch):
                categories.append(dict(UNCATEGORIZED))
            results.extend(categories[:len(batch)])
        except Exception as e:
            logger.error(f"Anthropic categorization failed: {e}")
            results.extend([dict(UNCATEGORIZED)] * len(batch))

    return results


async def categorize_transactions(transactions: list[dict]) -> list[dict]:
    provider = settings.ai_provider
    active_key = settings.anthropic_api_key if provider == "anthropic" else settings.openai_api_key

    if not active_key:
        logger.warning(f"No {provider} API key configured, skipping categorization")
        return [dict(UNCATEGORIZED)] * len(transactions)

    if provider == "anthropic":
        return await _categorize_anthropic(transactions)
    return await _categorize_openai(transactions)

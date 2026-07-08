import json
import logging

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


async def categorize_transactions(transactions: list[dict]) -> list[dict]:
    if not settings.openai_api_key:
        logger.warning("No OpenAI API key configured, skipping categorization")
        return [{"general_category": "Uncategorized", "precise_category": "Uncategorized"}] * len(transactions)

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    batch_size = 30
    results = []

    for i in range(0, len(transactions), batch_size):
        batch = transactions[i:i + batch_size]
        descriptions = [
            f"{idx+1}. {t['description']} | {t['original_amount']} {t['original_currency']} | {t['bank']}"
            for idx, t in enumerate(batch)
        ]

        prompt = f"""Categorize each transaction into the budget hierarchy below.

Categories:
{ALL_CATEGORIES_TEXT}

For each transaction, return the General Category (group name) and Precise Description (subcategory name).
Use EXACTLY the category names listed above.

Transactions:
{chr(10).join(descriptions)}

Return a JSON array with objects having "general_category" and "precise_category" fields.
Return ONLY the JSON array, no other text."""

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
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
                categories.append({"general_category": "Uncategorized", "precise_category": "Uncategorized"})
            results.extend(categories[:len(batch)])
        except Exception as e:
            logger.error(f"OpenAI categorization failed: {e}")
            results.extend([{"general_category": "Uncategorized", "precise_category": "Uncategorized"}] * len(batch))

    return results

import json
import logging
from abc import abstractmethod

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.config import settings
from app.services.agents.base import CATEGORY_HIERARCHY, UNCATEGORIZED, CategorizationAgent

logger = logging.getLogger(__name__)

BATCH_SIZE = 30

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


class LlmAgent(CategorizationAgent):
    """Chat-LLM agents: one batched prompt per BATCH_SIZE transactions."""

    async def classify(self, transactions: list[dict]) -> list[dict]:
        results = []
        for i in range(0, len(transactions), BATCH_SIZE):
            batch = transactions[i:i + BATCH_SIZE]
            try:
                categories = await self._complete_batch(_build_prompt(batch))
                while len(categories) < len(batch):
                    categories.append(dict(UNCATEGORIZED))
                results.extend(categories[:len(batch)])
            except Exception as e:
                logger.error(f"{self.label} categorization failed: {e}")
                results.extend([dict(UNCATEGORIZED) for _ in batch])
        return results

    @abstractmethod
    async def _complete_batch(self, prompt: str) -> list: ...


class OpenAiAgent(LlmAgent):
    provider = "openai"
    label = "OpenAI"
    env_var = "OPENAI_API_KEY"

    def is_configured(self) -> bool:
        return bool(settings.openai_api_key)

    async def _complete_batch(self, prompt: str) -> list:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        if isinstance(parsed, list):
            return parsed
        categories = parsed.get("categories", parsed.get("results", []))
        if not categories:
            for v in parsed.values():
                if isinstance(v, list):
                    categories = v
                    break
        return categories


class AnthropicAgent(LlmAgent):
    provider = "anthropic"
    label = "Anthropic"
    env_var = "ANTHROPIC_API_KEY"

    def is_configured(self) -> bool:
        return bool(settings.anthropic_api_key)

    async def _complete_batch(self, prompt: str) -> list:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": ANTHROPIC_RESULT_SCHEMA}},
        )
        text = next((block.text for block in response.content if block.type == "text"), "{}")
        return json.loads(text).get("results", [])

import json
import logging
import time
from abc import abstractmethod
from typing import NamedTuple

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app import agent_trace
from app.config import settings
from app.observability import elapsed_ms, log_event
from app.services.agents.base import UNCATEGORIZED, CategorizationAgent, Taxonomy, assignable_groups

logger = logging.getLogger(__name__)

BATCH_SIZE = 30


def _categories_text(categories: Taxonomy) -> str:
    return "\n".join(f"- {group}: {', '.join(cats)}" for group, cats in assignable_groups(categories).items())


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


def _build_prompt(batch: list[dict], categories: Taxonomy) -> str:
    """Build the identical categorization prompt used by both provider branches."""
    descriptions = [
        f"{idx+1}. {t['description']} | {t['original_amount']} {t['original_currency']} | {t['bank']}"
        for idx, t in enumerate(batch)
    ]

    return f"""Categorize each transaction into the budget hierarchy below.

Categories:
{_categories_text(categories)}

For each transaction, return the General Category (group name) and Precise Description (subcategory name).
Use EXACTLY the category names listed above.

Transactions:
{chr(10).join(descriptions)}

Return a JSON array with objects having "general_category" and "precise_category" fields.
Return ONLY the JSON array, no other text."""


PROMPT_HASH = agent_trace.prompt_hash(_build_prompt([], {}))


class BatchReply(NamedTuple):
    categories: list
    raw: str
    usage: dict | None


def _usage(response, in_attr: str, out_attr: str) -> dict | None:
    usage = getattr(response, "usage", None)
    tokens_in, tokens_out = getattr(usage, in_attr, None), getattr(usage, out_attr, None)
    if not all(isinstance(t, int) and not isinstance(t, bool) for t in (tokens_in, tokens_out)):
        return None
    return {"input_tokens": tokens_in, "output_tokens": tokens_out}


class LlmAgent(CategorizationAgent):
    """Chat-LLM agents: one batched prompt per BATCH_SIZE transactions."""

    async def classify(self, transactions: list[dict], categories: Taxonomy) -> list[dict]:
        if transactions and not assignable_groups(categories):
            log_event(
                logger, "agent_taxonomy", level=logging.WARNING, provider=self.provider, ok=False, reason="empty",
            )
            self.last_run_stats = {}
            return [dict(UNCATEGORIZED) for _ in transactions]
        tax_hash = agent_trace.taxonomy_hash(categories)
        results = []
        total_batches = -(-len(transactions) // BATCH_SIZE)
        failed_batches = 0
        total_padded = 0
        for i in range(0, len(transactions), BATCH_SIZE):
            batch = transactions[i:i + BATCH_SIZE]
            batch_no = i // BATCH_SIZE + 1
            batch_start = time.perf_counter()
            prompt = _build_prompt(batch, categories)
            trace = {
                "model": self.model, "stage": "batch", "batch": f"{batch_no}/{total_batches}",
                "size": len(batch), "prompt_hash": PROMPT_HASH,
                "taxonomy_hash": tax_hash, "input": {"prompt": prompt},
            }
            try:
                reply = await self._complete_batch(prompt)
                answers = reply.categories
                parsed = list(answers)
                padded = max(0, len(batch) - len(answers))
                while len(answers) < len(batch):
                    answers.append(dict(UNCATEGORIZED))
                results.extend(answers[:len(batch)])
                total_padded += padded
                ms = elapsed_ms(batch_start)
                log_event(
                    logger, "llm_batch", provider=self.provider, model=self.model,
                    batch=f"{batch_no}/{total_batches}", size=len(batch), ok=True, padded=padded,
                    ms=ms,
                )
                agent_trace.write(self.provider, {
                    **trace, "output": {"results": parsed, "raw": reply.raw}, "padded": padded,
                    "ms": ms, "attempts": None, "status": "ok", "status_code": None,
                    "cost": None, "usage": reply.usage,
                })
            except Exception as e:
                # Class and HTTP status only, never str(e): SDK error text can carry
                # key fragments or prompt text, and class + status already separates
                # auth (401), missing model (404), rate limit (429) and bad JSON.
                failed_batches += 1
                ms = elapsed_ms(batch_start)
                log_event(
                    logger, "llm_batch", level=logging.ERROR, provider=self.provider, model=self.model,
                    batch=f"{batch_no}/{total_batches}", size=len(batch), ok=False,
                    fallback="uncategorized", error=type(e).__name__,
                    status_code=getattr(e, "status_code", None), ms=ms,
                )
                agent_trace.write(self.provider, {
                    **trace, "output": None, "padded": None, "ms": ms, "attempts": None,
                    "status": type(e).__name__, "status_code": getattr(e, "status_code", None),
                    "cost": None, "usage": None,
                })
                results.extend([dict(UNCATEGORIZED) for _ in batch])
        self.last_run_stats = {
            "batches": total_batches, "failed_batches": failed_batches, "padded": total_padded,
        }
        return results

    @abstractmethod
    async def _complete_batch(self, prompt: str) -> BatchReply: ...


class OpenAiAgent(LlmAgent):
    provider = "openai"
    label = "OpenAI"
    env_var = "OPENAI_API_KEY"

    @property
    def model(self) -> str:
        return settings.openai_model

    def is_configured(self) -> bool:
        return bool(settings.openai_api_key)

    async def _complete_batch(self, prompt: str) -> BatchReply:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        usage = _usage(response, "prompt_tokens", "completion_tokens")
        if isinstance(parsed, list):
            return BatchReply(parsed, content, usage)
        categories = parsed.get("categories", parsed.get("results", []))
        if not categories:
            for v in parsed.values():
                if isinstance(v, list):
                    categories = v
                    break
        return BatchReply(categories, content, usage)


class AnthropicAgent(LlmAgent):
    provider = "anthropic"
    label = "Anthropic"
    env_var = "ANTHROPIC_API_KEY"

    @property
    def model(self) -> str:
        return settings.anthropic_model

    def is_configured(self) -> bool:
        return bool(settings.anthropic_api_key)

    async def _complete_batch(self, prompt: str) -> BatchReply:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": ANTHROPIC_RESULT_SCHEMA}},
        )
        text = next((block.text for block in response.content if block.type == "text"), "{}")
        categories = json.loads(text).get("results", [])
        return BatchReply(categories, text, _usage(response, "input_tokens", "output_tokens"))

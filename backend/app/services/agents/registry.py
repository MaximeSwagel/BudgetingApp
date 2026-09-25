import logging
from collections.abc import Callable

from app.services.agents.base import CategorizationAgent
from app.services.agents.jev import JevAgent
from app.services.agents.llm import AnthropicAgent, OpenAiAgent

logger = logging.getLogger(__name__)

# Zero-arg factories so a composite agent's factory can itself call build_agent.
AGENT_REGISTRY: dict[str, Callable[[], CategorizationAgent]] = {
    "openai": OpenAiAgent,
    "anthropic": AnthropicAgent,
    "openrouter": JevAgent,
}

DEFAULT_PROVIDER = "openai"


def build_agent(provider: str) -> CategorizationAgent:
    factory = AGENT_REGISTRY.get(provider)
    if factory is None:
        logger.warning(f"Unknown ai_provider {provider!r}, using {DEFAULT_PROVIDER}")
        factory = AGENT_REGISTRY[DEFAULT_PROVIDER]
    return factory()

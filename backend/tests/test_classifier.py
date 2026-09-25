import pytest

from app.config import settings
from app.services import classifier
from app.services.agents.base import UNCATEGORIZED, CategorizationAgent
from app.services.agents.jev import JevAgent
from app.services.agents.llm import AnthropicAgent, OpenAiAgent
from app.services.agents.registry import AGENT_REGISTRY, build_agent

TXNS = [
    {"description": "a", "original_amount": "1", "original_currency": "ILS", "bank": "Revolut"},
    {"description": "b", "original_amount": "2", "original_currency": "ILS", "bank": "Revolut"},
]
GOOD = {"general_category": "Household Expenses", "precise_category": "Groceries"}


class StubAgent(CategorizationAgent):
    provider = "stub"
    label = "Stub"
    env_var = "STUB_KEY"
    model = "stub-model"

    def __init__(self, result=None, configured=True, error=None):
        self.result, self.configured, self.error, self.called = result, configured, error, False

    def is_configured(self):
        return self.configured

    async def classify(self, transactions, categories):
        self.called = True
        self.categories = categories
        if self.error:
            raise self.error
        return self.result


def use(monkeypatch, agent):
    monkeypatch.setattr(classifier, "get_active_agent", lambda: agent)


def test_registry_maps_providers():
    assert set(AGENT_REGISTRY) == {"openai", "anthropic", "openrouter"}
    assert isinstance(build_agent("openai"), OpenAiAgent)
    assert isinstance(build_agent("anthropic"), AnthropicAgent)
    assert isinstance(build_agent("openrouter"), JevAgent)


def test_unknown_provider_falls_back_to_openai():
    assert isinstance(build_agent("nonsense"), OpenAiAgent)


def test_active_agent_follows_settings(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "openrouter")
    assert isinstance(classifier.get_active_agent(), JevAgent)
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    assert isinstance(classifier.get_active_agent(), AnthropicAgent)


@pytest.mark.asyncio
async def test_unconfigured_agent_returns_uncategorized_without_classify(monkeypatch):
    agent = StubAgent(result=[GOOD, GOOD], configured=False)
    use(monkeypatch, agent)

    out = await classifier.categorize_transactions(TXNS)

    assert out == [UNCATEGORIZED, UNCATEGORIZED]
    assert agent.called is False


@pytest.mark.asyncio
async def test_empty_input(monkeypatch):
    use(monkeypatch, StubAgent(result=[]))
    assert await classifier.categorize_transactions([]) == []


@pytest.mark.asyncio
async def test_result_passes_through(monkeypatch):
    use(monkeypatch, StubAgent(result=[GOOD, GOOD]))
    assert await classifier.categorize_transactions(TXNS) == [GOOD, GOOD]


@pytest.mark.asyncio
async def test_contract_guard_pads_truncates_and_replaces_non_dicts(monkeypatch):
    use(monkeypatch, StubAgent(result=[GOOD]))
    assert await classifier.categorize_transactions(TXNS) == [GOOD, UNCATEGORIZED]

    use(monkeypatch, StubAgent(result=[GOOD, GOOD, GOOD]))
    assert await classifier.categorize_transactions(TXNS) == [GOOD, GOOD]

    use(monkeypatch, StubAgent(result=[GOOD, "junk"]))
    assert await classifier.categorize_transactions(TXNS) == [GOOD, UNCATEGORIZED]


@pytest.mark.asyncio
async def test_raising_agent_gives_uncategorized(monkeypatch):
    use(monkeypatch, StubAgent(error=RuntimeError("x")))
    assert await classifier.categorize_transactions(TXNS) == [UNCATEGORIZED, UNCATEGORIZED]


@pytest.mark.asyncio
async def test_agent_receives_loaded_taxonomy_each_call(monkeypatch):
    loads = []

    async def load(session=None):
        loads.append(1)
        return {"G": ["C"]}

    monkeypatch.setattr(classifier, "load_category_hierarchy", load)
    agent = StubAgent(result=[GOOD, GOOD])
    use(monkeypatch, agent)
    await classifier.categorize_transactions(TXNS)
    await classifier.categorize_transactions(TXNS)
    assert agent.categories == {"G": ["C"]}
    assert len(loads) == 2


@pytest.mark.asyncio
async def test_unconfigured_agent_never_loads(monkeypatch):
    async def load(session=None):
        raise AssertionError("no load expected")

    monkeypatch.setattr(classifier, "load_category_hierarchy", load)
    use(monkeypatch, StubAgent(configured=False))
    assert await classifier.categorize_transactions(TXNS) == [UNCATEGORIZED, UNCATEGORIZED]


@pytest.mark.asyncio
async def test_loader_failure_degrades_to_uncategorized(monkeypatch):
    async def load(session=None):
        raise RuntimeError("db down")

    monkeypatch.setattr(classifier, "load_category_hierarchy", load)
    agent = StubAgent(result=[GOOD, GOOD])
    use(monkeypatch, agent)
    assert await classifier.categorize_transactions(TXNS) == [UNCATEGORIZED, UNCATEGORIZED]
    assert agent.called is False

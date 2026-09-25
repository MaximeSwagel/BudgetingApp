from abc import ABC, abstractmethod

Taxonomy = dict[str, list[str]]

UNCATEGORIZED = {"general_category": "Uncategorized", "precise_category": "Uncategorized"}


def assignable_groups(categories: Taxonomy) -> Taxonomy:
    """Groups with at least one subcategory: a line filed under any other could never be stored."""
    return {group: list(cats) for group, cats in categories.items() if cats}


class CategorizationAgent(ABC):
    """One way of turning parsed transactions into categories. The classifier
    service only knows this contract, so agents may batch, go line by line,
    or compose other agents."""

    provider: str
    label: str
    env_var: str
    # Optional counts for the llm_categorize log line; agents assign a fresh dict per classify.
    last_run_stats: dict = {}

    @property
    @abstractmethod
    def model(self) -> str: ...

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    async def classify(self, transactions: list[dict], categories: Taxonomy) -> list[dict]:
        """Return one {general_category, precise_category, [confidence]} per
        input, in the same order and length. `categories` is the ordered
        group -> subcategory names hierarchy the classifier loads from the DB
        on every call; agents never load it themselves or import DB code."""

from abc import ABC, abstractmethod

CATEGORY_HIERARCHY = {
    "Home Expenses": ["Rent", "Utilities: Gas, Electric, Water", "Internet, TV"],
    "Household Expenses": [
        "Groceries", "ATM Withdrawals", "Clothing", "Furniture & Equipment",
        "Laundry & Dry Cleaning", "Cell Phone",
    ],
    "Insurance, Tax & Bank Fees": [
        "Renters Insurance", "Other Insurance", "Income Tax", "Bank Fees", "Transfer Fees",
    ],
    "Health Care": ["Health Insurance", "Dental Insurance", "Doctor & Dentist"],
    "Discretionary": [
        "Restaurants & Coffee Shops", "Classes", "Subscriptions",
        "Concerts & Shows", "Gym/Sports", "Travel/Vacation",
    ],
}

UNCATEGORIZED = {"general_category": "Uncategorized", "precise_category": "Uncategorized"}


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
    async def classify(self, transactions: list[dict]) -> list[dict]:
        """Return one {general_category, precise_category, [confidence]} per
        input, in the same order and length."""

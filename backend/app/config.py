from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./budgetingapp.db"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    ai_provider: str = "openai"
    openai_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-haiku-4-5"
    base_currency: str = "ILS"
    # Default floor (in base currency) above which a recurring merchant is
    # flagged as a "large" recurring expense on the Analysis page. User-
    # overridable at runtime via /api/settings/recurring.
    recurring_large_threshold: float = 100.0
    # Destructive "clear all data" endpoint — enabled only in dev environments.
    allow_data_reset: bool = False

    model_config = {"env_file": ".env"}


settings = Settings()

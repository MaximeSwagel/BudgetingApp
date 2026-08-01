from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./budgetingapp.db"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    ai_provider: str = "openai"
    openai_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-haiku-4-5"
    base_currency: str = "ILS"
    # Destructive "clear all data" endpoint — enabled only in dev environments.
    allow_data_reset: bool = False

    model_config = {"env_file": ".env"}


settings = Settings()

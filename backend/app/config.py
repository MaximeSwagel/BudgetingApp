from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./budgetingapp.db"
    openai_api_key: str = ""
    base_currency: str = "ILS"

    model_config = {"env_file": ".env"}


settings = Settings()

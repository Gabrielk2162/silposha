from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./silposha.db"
    secret_key: str = "change-me-in-production"
    claude_api_key: str = ""
    silpo_default_filial_id: str = "2405"

    model_config = {"env_file": ".env", "env_prefix": "SILPOSHA_"}


settings = Settings()

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration from the environment. In Azure the secrets come from Key Vault."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str
    telegram_webhook_secret: str
    telegram_allowed_user_id: int
    database_url: str
    anthropic_api_key: str
    # Lookups are short and frequent, so low effort keeps them fast. Model and effort can be
    # changed per environment without a code change.
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    public_url: str | None = None

    # Only set for the release job, which manages the database.
    database_admin_url: str | None = None
    app_db_role: str | None = None
    app_db_password: str | None = None

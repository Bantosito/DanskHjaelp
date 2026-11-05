from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration from the environment. In Azure the secrets come from Key Vault."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str
    telegram_webhook_secret: str
    telegram_allowed_user_id: int
    database_url: str
    public_url: str | None = None

"""Run once per deploy, before traffic moves: migrate the database, register the webhook."""

import asyncio

from alembic import command
from alembic.config import Config
from telegram import Bot, Update

from danskhjaelp.config import Settings


async def register_webhook(settings: Settings) -> None:
    if not settings.public_url:
        raise SystemExit("PUBLIC_URL is required to register the Telegram webhook")
    async with Bot(settings.telegram_bot_token) as bot:
        await bot.set_webhook(
            url=f"{settings.public_url.rstrip('/')}/telegram/webhook",
            secret_token=settings.telegram_webhook_secret,
            allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY],
        )


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    command.upgrade(Config("alembic.ini"), "head")
    asyncio.run(register_webhook(settings))


if __name__ == "__main__":
    main()

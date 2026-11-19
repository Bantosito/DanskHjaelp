import asyncio
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Request, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from telegram import Update
from telegram.request import BaseRequest

from danskhjaelp.bot import Services, build_bot
from danskhjaelp.config import Settings
from danskhjaelp.db import make_sessions
from danskhjaelp.dictionary import ClaudeDictionary, Dictionary


def create_app(
    settings: Settings | None = None,
    request: BaseRequest | None = None,
    dictionary: Dictionary | None = None,
) -> FastAPI:
    settings = settings or Settings()  # type: ignore[call-arg]
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    dictionary = dictionary or ClaudeDictionary(
        settings.anthropic_api_key, settings.anthropic_model, settings.anthropic_effort
    )
    bot = build_bot(
        settings.telegram_bot_token,
        settings.telegram_allowed_user_id,
        Services(make_sessions(engine), dictionary),
        request,
    )
    bot_lock = asyncio.Lock()
    bot_ready = False

    async def ensure_bot() -> None:
        """Connect to Telegram on the first message, which keeps cold starts fast."""
        nonlocal bot_ready
        async with bot_lock:
            if not bot_ready:
                await bot.initialize()
                bot_ready = True

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if bot_ready:
            await bot.shutdown()
        await engine.dispose()

    app = FastAPI(title="DanskHjælp", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """The process is up. Used by Azure's liveness probe."""
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> dict[str, str]:
        """The process can reach its database. Used by the smoke test after a deploy."""
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception as error:
            raise HTTPException(status_code=503, detail="database unavailable") from error
        return {"status": "ready"}

    @app.post("/telegram/webhook")
    async def telegram_webhook(
        request: Request,
        secret: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
    ) -> Response:
        if not secret or not secrets.compare_digest(secret, settings.telegram_webhook_secret):
            raise HTTPException(status_code=403, detail="invalid secret")
        await ensure_bot()
        data: dict[str, Any] = await request.json()
        # Awaited rather than queued, so a replica can't scale to zero with work unfinished.
        await bot.process_update(Update.de_json(data, bot.bot))
        return Response(status_code=200)

    return app

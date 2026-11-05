from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from telegram.request import BaseRequest

GREETING = "Hej! Jeg er DanskHjælp."


async def greet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(GREETING)


def build_bot(token: str, allowed_user_id: int, request: BaseRequest | None = None) -> Application:  # type: ignore[type-arg]
    """Build the bot without a poller, because Telegram delivers updates by webhook."""
    builder = Application.builder().token(token).updater(None)
    if request is not None:
        builder = builder.request(request)
    bot = builder.build()
    # Anyone can message a Telegram bot, so everyone except me is ignored here.
    bot.add_handler(MessageHandler(filters.User(user_id=allowed_user_id), greet))
    return bot

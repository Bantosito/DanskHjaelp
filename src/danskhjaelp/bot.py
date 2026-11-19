import logging
from html import escape

import anthropic
from sqlalchemy.ext.asyncio import async_sessionmaker
from telegram import InlineKeyboardMarkup, LinkPreviewOptions, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)
from telegram.request import BaseRequest

from danskhjaelp import lookup
from danskhjaelp.cards import card_buttons, render_card
from danskhjaelp.dictionary import Dictionary, DictionaryError

log = logging.getLogger(__name__)

GREETING = (
    "Hej! Jeg er DanskHjælp. Send mig et ord, så forklarer jeg det og gemmer det til dig.\n\n"
    'Tip: send ordet med sætningen, du så det i, fx: stort — "Det var et stort problem"'
)
UNAVAILABLE = "Jeg kunne ikke slå det op lige nu. Prøv igen om lidt."
TOO_LONG = "Det er lidt langt. Send ét ord eller udtryk ad gangen (længere tekster kommer senere)."
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

Context = ContextTypes.DEFAULT_TYPE


class Services:
    def __init__(self, sessions: async_sessionmaker, dictionary: Dictionary) -> None:  # type: ignore[type-arg]
        self.sessions = sessions
        self.dictionary = dictionary


def services(context: Context) -> Services:
    found: Services = context.application.bot_data["services"]
    return found


async def reply(
    update: Update, text: str, reply_markup: InlineKeyboardMarkup | None = None
) -> None:
    chat = update.effective_chat
    if chat:
        await chat.send_message(
            text,
            parse_mode=ParseMode.HTML,
            link_preview_options=NO_PREVIEW,
            reply_markup=reply_markup,
        )


async def start(update: Update, context: Context) -> None:
    await reply(update, GREETING)


async def on_text(update: Update, context: Context) -> None:
    message = update.message
    if not message or not message.text:
        return
    user_data = context.user_data if context.user_data is not None else {}
    fixing = user_data.pop("fixing", None)
    found = services(context)
    await message.chat.send_action(ChatAction.TYPING)
    try:
        async with found.sessions() as session:
            if fixing is not None:
                corrected = await lookup.correct(session, found.dictionary, fixing, message.text)
                if corrected is None:
                    return
                item, note, accepted = corrected
                await reply(update, ("✅ " if accepted else "🤔 ") + note)
                if accepted:
                    await reply(update, render_card(item, 1), reply_markup=card_buttons(item))
                return
            if len(message.text) > lookup.MAX_LOOKUP_LENGTH:
                await reply(update, TOO_LONG)
                return
            result = await lookup.look_up(session, found.dictionary, message.text)
    except (DictionaryError, anthropic.APIError) as error:
        log.warning("Lookup failed: %s", error)
        await reply(update, UNAVAILABLE)
        return
    await reply(
        update,
        render_card(result.item, result.times_looked_up),
        reply_markup=card_buttons(result.item),
    )


async def on_button(update: Update, context: Context) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    action, _, raw_id = query.data.partition(":")
    item_id = int(raw_id)
    found = services(context)

    if action == "fix":
        if context.user_data is not None:
            context.user_data["fixing"] = item_id
        await reply(
            update, "Skriv, hvad der er forkert, fx: <i>det hedder et bord, ikke en bord</i>"
        )
        return

    async with found.sessions() as session:
        if action == "ignore":
            item = await lookup.set_status(session, item_id, "ignoreret")
            if item:
                await reply(update, f"Ok, jeg spørger dig ikke om <b>{escape(item.lemma)}</b>.")
            return
        if action == "en":
            if query.message:
                await query.message.chat.send_action(ChatAction.TYPING)
            try:
                explained = await lookup.english_explanation(session, found.dictionary, item_id)
            except (DictionaryError, anthropic.APIError) as error:
                log.warning("English explanation failed: %s", error)
                await reply(update, UNAVAILABLE)
                return
            if explained:
                item, text = explained
                await reply(update, f"🇬🇧 <b>{escape(item.lemma)}</b>\n{escape(text)}")


def build_bot(
    token: str,
    allowed_user_id: int,
    services_: Services,
    request: BaseRequest | None = None,
) -> Application:  # type: ignore[type-arg]
    """Build the bot without a poller, because Telegram delivers updates by webhook."""
    builder = Application.builder().token(token).updater(None)
    if request is not None:
        builder = builder.request(request)
    bot = builder.build()
    bot.bot_data["services"] = services_

    async def only_me(update: Update, context: Context) -> None:
        # Anyone can message a Telegram bot, so everyone except me is stopped here.
        user = update.effective_user
        if user is None or user.id != allowed_user_id:
            raise ApplicationHandlerStop

    bot.add_handler(TypeHandler(Update, only_me), group=-1)
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    bot.add_handler(CallbackQueryHandler(on_button))
    return bot

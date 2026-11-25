"""How entries look in Telegram. Telegram's HTML mode is used, so every value is escaped."""

from html import escape
from urllib.parse import quote

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from danskhjaelp.db import Item

POS_LABELS = {
    "substantiv": "sb.",
    "verbum": "vb.",
    "adjektiv": "adj.",
    "adverbium": "adv.",
    "pronomen": "pron.",
    "præposition": "præp.",
    "konjunktion": "konj.",
    "talord": "talord",
    "udtryk": "udtryk",
    "andet": "",
}


def ordnet_url(lemma: str) -> str:
    return f"https://ordnet.dk/ddo/ordbog?query={quote(lemma)}"


def render_card(item: Item, times_looked_up: int) -> str:
    label = POS_LABELS.get(item.part_of_speech, "")
    lines = [f"<b>{escape(item.lemma)}</b>" + (f" ({label})" if label else "")]
    lines.append(escape(item.forms_display))
    lines.append("")
    lines.append(f"🇩🇰 {escape(item.meaning_da)}")
    lines.append(f"🇬🇧 {escape(item.meaning_en)}")
    lines.append("")
    lines.append(f"<i>Eks:</i> {escape(item.example)}")
    if item.confusables:
        lines.append(f"<i>Pas på:</i> {escape(item.confusables)}")
    if item.uncertain and not item.verified:
        link = escape(ordnet_url(item.lemma), quote=True)
        lines.append(f'⚠️ Jeg er ikke helt sikker. <a href="{link}">Tjek i ordbogen</a>')
    if times_looked_up > 1:
        lines.append(f"\n🔁 Du har slået det op {times_looked_up} gange.")
    return "\n".join(lines)


def card_buttons(item: Item) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton("🇬🇧 Mere på engelsk", callback_data=f"en:{item.id}"),
        InlineKeyboardButton("✏️ Ret", callback_data=f"fix:{item.id}"),
    ]
    if item.status != "ignoreret":
        row.append(InlineKeyboardButton("🚫 Lær ikke", callback_data=f"ignore:{item.id}"))
    return InlineKeyboardMarkup([row])

"""Lookups: answer from the database when the word is known, otherwise ask the dictionary."""

import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from danskhjaelp.db import Item, Lookup
from danskhjaelp.dictionary import Dictionary, Entry

MAX_LOOKUP_LENGTH = 300
_SEPARATOR = re.compile(r"\s+[—–-]\s+|\n")
_EDGE_PUNCTUATION = " \t.,!?;:\"'«»“”„()"


@dataclass
class LookupResult:
    item: Item
    times_looked_up: int
    from_database: bool


def parse_query(text: str) -> tuple[str, str | None]:
    """Split 'stort — "Det var et stort problem"' into the word and the sentence it came from."""
    parts = _SEPARATOR.split(text.strip(), maxsplit=1)
    query = normalize(parts[0])
    context = parts[1].strip().strip(_EDGE_PUNCTUATION) if len(parts) > 1 else None
    return query, context or None


def normalize(text: str) -> str:
    return " ".join(text.lower().split()).strip(_EDGE_PUNCTUATION)


async def find_known(session: AsyncSession, query: str) -> Item | None:
    # Anything looked up before, including English words, maps straight to its item.
    earlier = await session.scalar(
        select(Item).join(Lookup).where(Lookup.query == query).order_by(Lookup.id.desc()).limit(1)
    )
    if earlier:
        return earlier
    return await session.scalar(
        select(Item)
        .where((Item.forms.contains([query])) | (func.lower(Item.lemma) == query))
        .order_by(Item.id)
        .limit(1)
    )


async def save_entry(session: AsyncSession, entry: Entry) -> Item:
    item = await session.scalar(
        select(Item).where(Item.lemma == entry.lemma, Item.part_of_speech == entry.part_of_speech)
    )
    if item is None:
        item = Item(lemma=entry.lemma, part_of_speech=entry.part_of_speech, status="set")
        session.add(item)
    elif item.verified:
        # A corrected entry wins over a fresh answer from the model.
        return item
    apply_entry(item, entry)
    return item


def apply_entry(item: Item, entry: Entry) -> None:
    item.lemma = entry.lemma
    item.part_of_speech = entry.part_of_speech
    item.gender = entry.gender
    item.forms = sorted({form.lower() for form in [entry.lemma, *entry.forms]})
    item.forms_display = entry.forms_display
    item.meaning_da = entry.meaning_da
    item.meaning_en = entry.meaning_en
    item.example = entry.example
    item.confusables = entry.confusables
    item.uncertain = entry.uncertain
    item.explanation_en = None


def entry_from(item: Item) -> Entry:
    return Entry.model_validate(
        {
            "lemma": item.lemma,
            "part_of_speech": item.part_of_speech,
            "gender": item.gender,
            "forms": item.forms,
            "forms_display": item.forms_display,
            "meaning_da": item.meaning_da,
            "meaning_en": item.meaning_en,
            "example": item.example,
            "confusables": item.confusables,
            "uncertain": item.uncertain,
            "direction": "da-en",
        }
    )


async def look_up(session: AsyncSession, dictionary: Dictionary, text: str) -> LookupResult:
    query, context = parse_query(text)
    item = await find_known(session, query)
    from_database = item is not None
    if item is None:
        entry = await dictionary.look_up(text.strip())
        item = await save_entry(session, entry)
        await session.flush()
        direction = entry.direction
    else:
        direction = "da-en" if query in item.forms or query == item.lemma.lower() else "en-da"

    earlier = await session.scalar(select(func.count()).where(Lookup.item_id == item.id)) or 0
    if earlier and item.status == "set":
        item.status = "lærer"
    session.add(Lookup(item_id=item.id, query=query, context_sentence=context, direction=direction))
    await session.commit()
    return LookupResult(item=item, times_looked_up=earlier + 1, from_database=from_database)


async def english_explanation(
    session: AsyncSession, dictionary: Dictionary, item_id: int
) -> tuple[Item, str] | None:
    item = await session.get(Item, item_id)
    if item is None:
        return None
    if item.explanation_en is None:
        item.explanation_en = await dictionary.explain_in_english(entry_from(item))
    latest = await session.scalar(
        select(Lookup).where(Lookup.item_id == item_id).order_by(Lookup.id.desc()).limit(1)
    )
    if latest:
        # Needing English is a signal worth tracking: these words get more practice later.
        latest.used_english = True
    await session.commit()
    return item, item.explanation_en


async def set_status(session: AsyncSession, item_id: int, status: str) -> Item | None:
    item = await session.get(Item, item_id)
    if item:
        item.status = status
        await session.commit()
    return item


async def correct(
    session: AsyncSession, dictionary: Dictionary, item_id: int, correction: str
) -> tuple[Item, str, bool] | None:
    item = await session.get(Item, item_id)
    if item is None:
        return None
    result = await dictionary.correct(entry_from(item), correction)
    if result.accepted:
        apply_entry(item, result.entry)
        item.verified = True
    await session.commit()
    return item, result.note_da, result.accepted

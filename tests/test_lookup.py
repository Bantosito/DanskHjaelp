import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from danskhjaelp import lookup
from danskhjaelp.cards import render_card
from danskhjaelp.db import Item, Lookup
from tests.conftest import STOR, FakeDictionary


@pytest.mark.parametrize(
    ("text", "query", "context"),
    [
        ("stort", "stort", None),
        ("  Stort! ", "stort", None),
        ('stort — "Det var et stort problem"', "stort", "Det var et stort problem"),
        ("stort - Det var et stort problem.", "stort", "Det var et stort problem"),
        ("stort\nDet var et stort problem", "stort", "Det var et stort problem"),
        ("det går nok", "det går nok", None),
        ("kort-tids", "kort-tids", None),
    ],
)
def test_parse_query(text: str, query: str, context: str | None) -> None:
    assert lookup.parse_query(text) == (query, context)


def test_card_escapes_html() -> None:
    item = Item(id=1, part_of_speech="adjektiv", verified=False, status="set")
    lookup.apply_entry(item, STOR.model_copy(update={"example": "<b>x</b> & y", "uncertain": True}))
    card = render_card(item, 3)
    assert "&lt;b&gt;x&lt;/b&gt; &amp; y" in card
    assert "ordnet.dk/ddo/ordbog?query=stor" in card
    assert "3 gange" in card


@pytest.mark.db
async def test_new_word_is_asked_once_then_answered_from_the_database(
    session: AsyncSession, dictionary: FakeDictionary
) -> None:
    first = await lookup.look_up(session, dictionary, "stort")
    assert not first.from_database
    assert first.item.lemma == "stor"
    assert first.item.status == "set"

    # A different form of the same word is found without asking the model again.
    second = await lookup.look_up(session, dictionary, "større")
    assert second.from_database
    assert second.item.id == first.item.id
    assert second.times_looked_up == 2
    assert second.item.status == "lærer"
    assert dictionary.lookups == ["stort"]

    queries = (await session.scalars(select(Lookup.query).order_by(Lookup.id))).all()
    assert queries == ["stort", "større"]


@pytest.mark.db
async def test_english_lookups_are_remembered(
    session: AsyncSession, dictionary: FakeDictionary
) -> None:
    first = await lookup.look_up(session, dictionary, "proud")
    assert first.item.lemma == "stolt"
    again = await lookup.look_up(session, dictionary, "Proud")
    assert again.from_database
    assert dictionary.lookups == ["proud"]
    directions = (await session.scalars(select(Lookup.direction))).all()
    assert set(directions) == {"en-da"}


@pytest.mark.db
async def test_context_sentence_is_saved(session: AsyncSession, dictionary: FakeDictionary) -> None:
    await lookup.look_up(session, dictionary, 'stort — "Det var et stort problem"')
    saved = await session.scalar(select(Lookup))
    assert saved is not None
    assert saved.context_sentence == "Det var et stort problem"


@pytest.mark.db
async def test_english_explanation_is_cached_and_tracked(
    session: AsyncSession, dictionary: FakeDictionary
) -> None:
    result = await lookup.look_up(session, dictionary, "stort")
    for _ in range(2):
        explained = await lookup.english_explanation(session, dictionary, result.item.id)
        assert explained is not None
    assert dictionary.explanations == 1
    saved = await session.scalar(select(Lookup))
    assert saved is not None and saved.used_english


@pytest.mark.db
async def test_ignored_words_stay_ignored(
    session: AsyncSession, dictionary: FakeDictionary
) -> None:
    result = await lookup.look_up(session, dictionary, "stort")
    await lookup.set_status(session, result.item.id, "ignoreret")
    again = await lookup.look_up(session, dictionary, "stort")
    assert again.item.status == "ignoreret"


@pytest.mark.db
async def test_accepted_correction_is_kept(
    session: AsyncSession, dictionary: FakeDictionary
) -> None:
    result = await lookup.look_up(session, dictionary, "stort")
    corrected = await lookup.correct(session, dictionary, result.item.id, "big")
    assert corrected is not None
    item, _, accepted = corrected
    assert accepted and item.verified and item.meaning_en == "big"

    # A corrected word is never overwritten by a fresh answer from the model.
    saved = await lookup.save_entry(session, STOR)
    assert saved.meaning_en == "big"


@pytest.mark.db
async def test_rejected_correction_changes_nothing(
    session: AsyncSession, dictionary: FakeDictionary
) -> None:
    dictionary.accept_corrections = False
    result = await lookup.look_up(session, dictionary, "stort")
    corrected = await lookup.correct(session, dictionary, result.item.id, "small")
    assert corrected is not None
    item, note, accepted = corrected
    assert not accepted and not item.verified and item.meaning_en == STOR.meaning_en
    assert note

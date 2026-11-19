import json
import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from telegram.request import BaseRequest, RequestData

from danskhjaelp.dictionary import Correction, Entry
from danskhjaelp.release import run_migrations

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
TABLES = "item_sources, chunks, documents, lookups, items"

STOR = Entry(
    lemma="stor",
    part_of_speech="adjektiv",
    gender=None,
    forms=["stor", "stort", "store", "større", "størst"],
    forms_display="stor · stort · store — større · størst",
    meaning_da="Noget, der fylder meget.",
    meaning_en="big, large, great",
    example="Det var et stort problem for dem.",
    confusables="stor ≠ høj (om personer)",
    uncertain=False,
    direction="da-en",
)
STOLT = Entry(
    lemma="stolt",
    part_of_speech="adjektiv",
    gender=None,
    forms=["stolt", "stolte", "stoltere", "stoltest"],
    forms_display="stolt · stolt · stolte — stoltere · stoltest",
    meaning_da="Glad og tilfreds med noget, man har gjort.",
    meaning_en="proud",
    example="Hun er stolt af sin søn.",
    confusables=None,
    uncertain=False,
    direction="en-da",
)


class FakeDictionary:
    """Answers from a fixed table and counts calls, so tests can see when the model was asked."""

    def __init__(self) -> None:
        self.entries = {"stort": STOR, "stor": STOR, "proud": STOLT}
        self.lookups: list[str] = []
        self.explanations = 0
        self.accept_corrections = True

    async def look_up(self, text: str) -> Entry:
        self.lookups.append(text)
        word = text.split(" — ")[0].strip().lower()
        return self.entries[word]

    async def correct(self, entry: Entry, correction: str) -> Correction:
        if not self.accept_corrections:
            return Correction(accepted=False, note_da="Det er rigtigt som det står.", entry=entry)
        fixed = entry.model_copy(update={"meaning_en": correction})
        return Correction(accepted=True, note_da="Rettet.", entry=fixed)

    async def explain_in_english(self, entry: Entry) -> str:
        self.explanations += 1
        return f"'{entry.lemma}' means {entry.meaning_en} & is common."


class FakeTelegram(BaseRequest):
    """Stands in for Telegram's servers and records what the bot sends."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.connected = False

    @property
    def sent(self) -> list[dict[str, Any]]:
        return [parameters for method, parameters in self.calls if method == "sendMessage"]

    @property
    def read_timeout(self) -> float:
        return 1.0

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def do_request(  # type: ignore[override]
        self, url: str, method: str, request_data: RequestData | None = None, **_: Any
    ) -> tuple[int, bytes]:
        api_method = url.rsplit("/", 1)[-1]
        parameters = request_data.parameters if request_data else {}
        result: Any
        if api_method == "getMe":
            self.connected = True
            result = {"id": 1, "is_bot": True, "first_name": "Bot", "username": "test_bot"}
        elif api_method == "sendMessage":
            self.calls.append((api_method, parameters))
            result = {
                "message_id": 2,
                "date": 0,
                "chat": {"id": parameters.get("chat_id", 0), "type": "private"},
            }
        else:
            self.calls.append((api_method, parameters))
            result = True
        return 200, json.dumps({"ok": True, "result": result}).encode()


@pytest.fixture
def dictionary() -> FakeDictionary:
    return FakeDictionary()


@pytest.fixture
def telegram() -> FakeTelegram:
    return FakeTelegram()


@pytest.fixture(scope="session")
def migrated_database() -> str:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set")
    run_migrations(TEST_DATABASE_URL)
    return TEST_DATABASE_URL


@pytest.fixture
def clean_database(migrated_database: str) -> Iterator[str]:
    engine = create_engine(migrated_database)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    engine.dispose()
    yield migrated_database


@pytest.fixture
async def session(clean_database: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(clean_database)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()

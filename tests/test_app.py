from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from danskhjaelp.bot import GREETING
from danskhjaelp.config import Settings
from danskhjaelp.main import create_app
from tests.conftest import FakeDictionary, FakeTelegram

ME = 111
STRANGER = 222
SECRET = "test-secret"
HEADERS = {"X-Telegram-Bot-Api-Secret-Token": SECRET}


def message_from(user_id: int, text: str = "/start") -> dict[str, Any]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "text": text,
            **(
                {"entities": [{"type": "bot_command", "offset": 0, "length": len(text)}]}
                if text.startswith("/")
                else {}
            ),
        },
    }


def make_settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        telegram_bot_token="1:test",
        telegram_webhook_secret=SECRET,
        telegram_allowed_user_id=ME,
        database_url=database_url,
        anthropic_api_key="test",
    )


@pytest.fixture
def client(telegram: FakeTelegram, dictionary: FakeDictionary) -> Iterator[TestClient]:
    settings = make_settings("postgresql+psycopg://nobody:nothing@localhost:1/none")
    with TestClient(create_app(settings, telegram, dictionary)) as test_client:
        yield test_client


@pytest.fixture
def db_client(
    telegram: FakeTelegram, dictionary: FakeDictionary, clean_database: str
) -> Iterator[TestClient]:
    settings = make_settings(clean_database)
    with TestClient(create_app(settings, telegram, dictionary)) as test_client:
        yield test_client


def test_healthz(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_startup_does_not_contact_telegram(client: TestClient, telegram: FakeTelegram) -> None:
    client.get("/healthz")
    assert not telegram.connected


def test_readyz_reports_unreachable_database(client: TestClient) -> None:
    assert client.get("/readyz").status_code == 503


def test_webhook_rejects_missing_secret(client: TestClient, telegram: FakeTelegram) -> None:
    assert client.post("/telegram/webhook", json=message_from(ME)).status_code == 403
    assert telegram.sent == []


def test_webhook_rejects_wrong_secret(client: TestClient, telegram: FakeTelegram) -> None:
    response = client.post(
        "/telegram/webhook",
        json=message_from(ME),
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )
    assert response.status_code == 403
    assert telegram.sent == []


def test_start_gets_danish_greeting(client: TestClient, telegram: FakeTelegram) -> None:
    response = client.post("/telegram/webhook", json=message_from(ME), headers=HEADERS)
    assert response.status_code == 200
    assert [message["text"] for message in telegram.sent] == [GREETING]


def test_other_users_are_ignored(client: TestClient, telegram: FakeTelegram) -> None:
    response = client.post("/telegram/webhook", json=message_from(STRANGER), headers=HEADERS)
    assert response.status_code == 200
    assert telegram.sent == []


def button_from(user_id: int, data: str) -> dict[str, Any]:
    return {
        "update_id": 2,
        "callback_query": {
            "id": "cb1",
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "chat_instance": "1",
            "data": data,
            "message": message_from(user_id, "card")["message"],
        },
    }


@pytest.mark.db
def test_lookup_replies_with_a_card(db_client: TestClient, telegram: FakeTelegram) -> None:
    response = db_client.post("/telegram/webhook", json=message_from(ME, "stort"), headers=HEADERS)
    assert response.status_code == 200
    card = telegram.sent[-1]
    assert card["parse_mode"] == "HTML"
    assert "<b>stor</b> (adj.)" in card["text"]
    assert "big, large, great" in card["text"]
    buttons = [b["callback_data"] for b in card["reply_markup"]["inline_keyboard"][0]]
    assert buttons == ["en:1", "fix:1", "ignore:1"]


@pytest.mark.db
def test_correction_flow(
    db_client: TestClient, telegram: FakeTelegram, dictionary: FakeDictionary
) -> None:
    db_client.post("/telegram/webhook", json=message_from(ME, "stort"), headers=HEADERS)
    db_client.post("/telegram/webhook", json=button_from(ME, "fix:1"), headers=HEADERS)
    assert "Skriv" in telegram.sent[-1]["text"]
    db_client.post("/telegram/webhook", json=message_from(ME, "big"), headers=HEADERS)
    assert telegram.sent[-2]["text"].startswith("✅")
    assert "🇬🇧 big" in telegram.sent[-1]["text"]
    # The correction was applied, not looked up as a new word.
    assert dictionary.lookups == ["stort"]


@pytest.mark.db
def test_english_button(db_client: TestClient, telegram: FakeTelegram) -> None:
    db_client.post("/telegram/webhook", json=message_from(ME, "stort"), headers=HEADERS)
    db_client.post("/telegram/webhook", json=button_from(ME, "en:1"), headers=HEADERS)
    assert "means big, large, great &amp; is common" in telegram.sent[-1]["text"]
    assert ("answerCallbackQuery", {"callback_query_id": "cb1"}) in telegram.calls


def test_strangers_buttons_are_ignored(client: TestClient, telegram: FakeTelegram) -> None:
    client.post("/telegram/webhook", json=button_from(STRANGER, "ignore:1"), headers=HEADERS)
    assert telegram.calls == []

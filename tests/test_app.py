import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from telegram.request import BaseRequest, RequestData

from danskhjaelp.bot import GREETING
from danskhjaelp.config import Settings
from danskhjaelp.main import create_app

ME = 111
STRANGER = 222
SECRET = "test-secret"
HEADERS = {"X-Telegram-Bot-Api-Secret-Token": SECRET}


class FakeTelegram(BaseRequest):
    """Stands in for Telegram's servers and records what the bot sends."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.connected = False

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
        result: dict[str, Any]
        if url.endswith("/getMe"):
            self.connected = True
            result = {"id": 1, "is_bot": True, "first_name": "Bot", "username": "test_bot"}
        else:
            parameters = request_data.parameters if request_data else {}
            self.sent.append(parameters)
            result = {
                "message_id": 2,
                "date": 0,
                "chat": {"id": parameters.get("chat_id", 0), "type": "private"},
            }
        return 200, json.dumps({"ok": True, "result": result}).encode()


def message_from(user_id: int) -> dict[str, Any]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "text": "stort",
        },
    }


@pytest.fixture
def telegram() -> FakeTelegram:
    return FakeTelegram()


@pytest.fixture
def client(telegram: FakeTelegram) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        telegram_bot_token="1:test",
        telegram_webhook_secret=SECRET,
        telegram_allowed_user_id=ME,
        database_url="postgresql+psycopg://nobody:nothing@localhost:1/none",
    )
    with TestClient(create_app(settings, telegram)) as test_client:
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


def test_allowed_user_gets_danish_reply(client: TestClient, telegram: FakeTelegram) -> None:
    response = client.post("/telegram/webhook", json=message_from(ME), headers=HEADERS)
    assert response.status_code == 200
    assert [message["text"] for message in telegram.sent] == [GREETING]


def test_other_users_are_ignored(client: TestClient, telegram: FakeTelegram) -> None:
    response = client.post("/telegram/webhook", json=message_from(STRANGER), headers=HEADERS)
    assert response.status_code == 200
    assert telegram.sent == []

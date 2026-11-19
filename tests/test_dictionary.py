from types import SimpleNamespace
from typing import Any

import pytest

from danskhjaelp.dictionary import ClaudeDictionary, DictionaryError, Entry
from tests.conftest import STOR


class FakeMessages:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response


def dictionary_with(response: Any) -> tuple[ClaudeDictionary, FakeMessages]:
    messages = FakeMessages(response)
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return ClaudeDictionary("key", "claude-opus-5-5", "low", client=client), messages  # type: ignore[arg-type]


async def test_look_up_returns_the_parsed_entry() -> None:
    dictionary, messages = dictionary_with(
        SimpleNamespace(stop_reason="end_turn", parsed_output=STOR)
    )
    assert await dictionary.look_up("stort") == STOR
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_format"] is Entry
    assert call["output_config"] == {"effort": "low"}
    assert call["fallbacks"] == "default"


async def test_refusal_is_an_error() -> None:
    dictionary, _ = dictionary_with(SimpleNamespace(stop_reason="refusal", parsed_output=None))
    with pytest.raises(DictionaryError):
        await dictionary.look_up("stort")


async def test_explanation_joins_text_blocks() -> None:
    blocks = [
        SimpleNamespace(type="thinking", thinking=""),
        SimpleNamespace(type="text", text="Big. "),
    ]
    dictionary, _ = dictionary_with(SimpleNamespace(stop_reason="end_turn", content=blocks))
    assert await dictionary.explain_in_english(STOR) == "Big."


def test_entry_schema_is_strict() -> None:
    # Structured outputs need every object closed, so unexpected fields can't slip through.
    schema = Entry.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(Entry.model_fields)

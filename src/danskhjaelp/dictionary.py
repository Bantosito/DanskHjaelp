"""The Claude-backed dictionary: explains Danish words and turns them into structured entries."""

import json
from typing import Literal, Protocol

import anthropic
from anthropic.types.beta import BetaOutputConfigParam
from pydantic import BaseModel, ConfigDict

PartOfSpeech = Literal[
    "substantiv",
    "verbum",
    "adjektiv",
    "adverbium",
    "pronomen",
    "præposition",
    "konjunktion",
    "talord",
    "udtryk",
    "andet",
]


Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lemma: str
    part_of_speech: PartOfSpeech
    gender: Literal["en", "et"] | None
    forms: list[str]
    forms_display: str
    meaning_da: str
    meaning_en: str
    example: str
    confusables: str | None
    uncertain: bool
    direction: Literal["da-en", "en-da"]


class Correction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    note_da: str
    entry: Entry


class DictionaryError(Exception):
    """The dictionary couldn't produce an answer. The message is safe to log, not to show."""


class Dictionary(Protocol):
    async def look_up(self, text: str) -> Entry: ...

    async def correct(self, entry: Entry, correction: str) -> Correction: ...

    async def explain_in_english(self, entry: Entry) -> str: ...


SYSTEM = """You are the dictionary inside DanskHjælp, a Danish learning bot. The learner is an adult \
at intermediate level (lavere mellemniveau) who knows English.

The user message is a lookup: a Danish word or phrase in any inflected form, or an English word or \
phrase to translate into Danish. It may be followed by the sentence where the learner met it; use \
that sentence to choose the right meaning.

Return one entry for the Danish headword:
- lemma: the dictionary form (stort → stor, købte → købe, huset → hus). For a phrase, its usual form.
- part_of_speech
- gender: "en" or "et" for nouns, otherwise null.
- forms: every inflected form in lowercase, including the lemma. Nouns: indefinite and definite, \
singular and plural (bil, bilen, biler, bilerne). Verbs: infinitive, present, past, past participle \
(købe, køber, købte, købt). Adjectives: common, neuter and plural/definite, plus comparative and \
superlative when they exist (stor, stort, store, større, størst). Phrases: just the phrase.
- forms_display: the forms as a learner reads them, for example "stor · stort · store — større · \
størst", "en bil · bilen · biler · bilerne" or "at købe · køber · købte · har købt".
- meaning_da: a short explanation in simple Danish at the learner's level, never just the English word.
- meaning_en: the English translation, with alternatives separated by commas.
- example: one natural, everyday Danish sentence using the word. If the learner gave a sentence, \
you may use it.
- confusables: a short Danish note about a word it is commonly confused with, like \
"stor ≠ høj (om personer)", or null when there is no common confusion.
- uncertain: true when you are not sure about the forms, gender or meaning, for example for rare, \
slang or regional words, or ambiguous input. A wrong entry teaches the learner a mistake they will \
drill for weeks, so mark uncertainty rather than guess.
- direction: "da-en" if the lookup was Danish, "en-da" if it was English.

Follow standard Danish spelling and inflection as in Den Danske Ordbog and Retskrivningsordbogen."""

CORRECTION = """The learner tapped "Ret" on this entry and sent a correction. Learners are sometimes \
wrong. If the correction is right in standard Danish, apply it and set accepted to true. If it is \
wrong, return the entry unchanged and set accepted to false. Either way, write note_da: one or two \
short sentences in simple Danish saying what changed or why it was not changed."""

ENGLISH = """Explain this Danish word to the learner in English, in at most 120 words: what it \
means, how it is used, any grammar that trips learners up (gender, irregular forms, word order), \
and how it differs from words it is confused with. Plain text only, no markdown."""


class ClaudeDictionary:
    def __init__(
        self,
        api_key: str,
        model: str,
        effort: Effort,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self._client = client or anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._output_config: BetaOutputConfigParam = {"effort": effort}

    async def look_up(self, text: str) -> Entry:
        return await self._parse(text, Entry)

    async def correct(self, entry: Entry, correction: str) -> Correction:
        message = f"{CORRECTION}\n\nEntry:\n{entry.model_dump_json()}\n\nCorrection:\n{correction}"
        return await self._parse(message, Correction)

    async def explain_in_english(self, entry: Entry) -> str:
        response = await self._client.beta.messages.create(
            model=self._model,
            max_tokens=4000,
            system=SYSTEM,
            output_config=self._output_config,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[
                {"role": "user", "content": f"{ENGLISH}\n\n{json.dumps(entry.model_dump())}"}
            ],
        )
        if response.stop_reason == "refusal":
            raise DictionaryError("the model declined to explain this entry")
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise DictionaryError(f"no explanation returned (stop reason {response.stop_reason})")
        return text

    async def _parse[T: BaseModel](self, message: str, output: type[T]) -> T:
        response = await self._client.beta.messages.parse(
            model=self._model,
            max_tokens=4000,
            system=SYSTEM,
            output_config=self._output_config,
            output_format=output,
            # If the model declines, the API retries on a fallback model in the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": message}],
        )
        if response.stop_reason == "refusal":
            raise DictionaryError("the model declined this lookup")
        if response.parsed_output is None:
            raise DictionaryError(f"no entry returned (stop reason {response.stop_reason})")
        return response.parsed_output

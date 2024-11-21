# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 vionya
from __future__ import annotations

import re
from datetime import datetime
from functools import cached_property

from yarl import URL

URBAN_DICT = URL("https://urbandictionary.com/define.php")
URBAN_DICT_PAT = re.compile(r"\[(.+?)\]")


class StandardDictionaryDefinition:
    __slots__ = ("definition", "example", "synonyms")

    def __init__(self, definition_data):
        self.definition = definition_data.pop("definition")
        self.example = definition_data.pop("example", None)
        self.synonyms = definition_data.pop("synonyms", None)

    def __repr__(self):
        return "<{0.__class__.__name__} definition={0.definition!r}>".format(
            self
        )


class StandardDictionaryMeaning:
    __slots__ = ("part_of_speech", "definitions")

    def __init__(self, meaning_data):
        self.part_of_speech = meaning_data.pop("partOfSpeech")
        self.definitions = [
            *map(StandardDictionaryDefinition, meaning_data.pop("definitions"))
        ]

    def __repr__(self):
        return "<{0.__class__.__name__} part_of_speech={0.part_of_speech!r} definitions={1}>".format(
            self, len(self.definitions)
        )


class StandardDictionaryWord:
    __slots__ = ("word", "phonetics", "meanings")

    def __init__(self, word_data):
        self.word = word_data.pop("word")
        self.phonetics = word_data.pop("phonetics")
        self.meanings = [
            *map(StandardDictionaryMeaning, word_data.pop("meanings"))
        ]

    def __repr__(self):
        return "<{0.__class__.__name__} word={0.word!r} meanings={1}>".format(
            self, len(self.meanings)
        )


class StandardDictionaryResponse:
    __slots__ = ("words",)

    def __init__(self, response_data):
        self.words = [*map(StandardDictionaryWord, response_data)]


class UrbanDictionaryTerm:
    __slots__ = (
        "_definition",
        "permalink",
        "thumbs_up",
        "author",
        "word",
        "defid",
        "current_vote",
        "_written_on",
        "_example",
        "thumbs_down",
        "__dict__",
    )

    _definition: str
    permalink: str
    thumbs_up: int
    author: str
    word: str
    defid: int
    current_vote: str
    _written_on: str
    _example: str
    thumbs_down: int

    def __init__(self, term_data: dict):
        self._definition = term_data.pop("definition")
        self.permalink = term_data.pop("permalink")
        self.thumbs_up = term_data.pop("thumbs_up")
        self.author = term_data.pop("author")
        self.word = term_data.pop("word")
        self.defid = term_data.pop("defid")
        self.current_vote = term_data.pop("current_vote")
        self._written_on = term_data.pop("written_on")
        self._example = term_data.pop("example")
        self.thumbs_down = term_data.pop("thumbs_down")

    @cached_property
    def written_on(self) -> datetime:
        return datetime.fromisoformat(self._written_on.removesuffix("Z"))

    @staticmethod
    def transform_hyperlinks(content: str) -> str:
        for mat in URBAN_DICT_PAT.findall(content):
            content = content.replace(
                f"[{mat}]", f"[{mat}]({URBAN_DICT % {'term': mat}})"
            )
        return content

    @cached_property
    def definition(self) -> str:
        return self.transform_hyperlinks(self._definition)

    @cached_property
    def example(self) -> str:
        return self.transform_hyperlinks(self._example)


class UrbanDictionaryResponse:
    __slots__ = ("results",)

    def __init__(self, response_data):
        self.results = [*map(UrbanDictionaryTerm, response_data["list"])]

    def __iter__(self):
        return iter(self.results)

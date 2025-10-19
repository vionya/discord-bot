# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 vionya
from typing import Optional

from aiohttp import ClientSession
from yarl import URL

from .objects import StandardDictionaryResponse, UrbanDictionaryResponse

BASE_STANDARD = URL("https://api.dictionaryapi.dev/api/v2/entries/")
BASE_URBAN = URL("https://api.urbandictionary.com/v0/define")


class DefinitionError(Exception):
    def __init__(self, status: int):
        super().__init__()
        self.status = status


class Define:
    __slots__ = ("session",)

    def __init__(self, session: Optional[ClientSession] = None):
        self.session = session or ClientSession()

    async def define_standard(self, query: str):
        url = BASE_STANDARD / "en" / query

        async with self.session.get(url) as resp:
            if resp.status != 200:
                raise DefinitionError(resp.status)
            _data = await resp.json()

        return StandardDictionaryResponse(_data)

    async def define_urban(self, query: str):
        url = BASE_URBAN % {"term": query}

        async with self.session.get(url) as resp:
            if resp.status != 200:
                raise DefinitionError(resp.status)
            _data = await resp.json()

        return UrbanDictionaryResponse(_data)

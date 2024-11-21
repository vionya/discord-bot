# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 vionya
from typing import Optional

from aiohttp import ClientSession
from yarl import URL

from .objects import StandardDictionaryResponse, UrbanDictionaryResponse

BASE_STANDARD = URL("https://api.dictionaryapi.dev/api/v2/entries/")
BASE_URBAN = URL("https://api.urbandictionary.com/v0/define")
DefinitionError = type("DefinitionError", (Exception,), {})


class Define:
    __slots__ = ("session",)

    def __init__(self, session: Optional[ClientSession] = None):
        self.session = session or ClientSession()

    async def define_standard(self, query: str):
        url = BASE_STANDARD / "en" / query

        async with self.session.get(url) as resp:
            _data = await resp.json()
            if resp.status != 200:
                raise DefinitionError(
                    f"Error fetching standard dictionary definition ({resp.status})"
                )

        return StandardDictionaryResponse(_data)

    async def define_urban(self, query: str):
        url = BASE_URBAN % {"term": query}

        async with self.session.get(url) as resp:
            _data = await resp.json()
            if resp.status != 200:
                raise DefinitionError(
                    f"Error fetching Urban Dictionary definition ({resp.status})"
                )

        return UrbanDictionaryResponse(_data)

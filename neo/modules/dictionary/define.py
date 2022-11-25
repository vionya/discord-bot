# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from typing import Optional

from aiohttp import ClientSession
from yarl import URL

from .objects import DictionaryResponse

BASE = URL("https://api.dictionaryapi.dev/api/v2/entries/")
DefinitionError = type("DefinitionError", (Exception,), {})


class Define:
    __slots__ = ("session",)

    def __init__(self, session: Optional[ClientSession] = None):
        self.session = session or ClientSession()

    async def _do_definition(self, query: str):
        url = BASE / "en" / query

        async with self.session.get(url) as resp:

            _data = await resp.json()
            if resp.status != 200:
                raise DefinitionError(
                    f"Error fetching definition ({resp.status})"
                )

        return DictionaryResponse(_data)

    def define(self, query):
        return self._do_definition(query)

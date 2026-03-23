# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2020-present vionya
from typing import Optional
import xml.etree.ElementTree as Tree

from aiohttp import ClientSession
from yarl import URL

SUGGEST_BASE = URL(
    "https://clients1.google.com/complete/search?hl=en&output=toolbar"
)
GoogleError = type("GoogleError", (Exception,), {})


class Suggest:
    __slots__ = ("session",)

    def __init__(
        self,
        *,
        session: Optional[ClientSession] = None,
    ):
        self.session = session or ClientSession()

    async def suggest(self, term: str):
        async with self.session.get(SUGGEST_BASE.extend_query(q=term)) as resp:
            if resp.status != 200:
                raise GoogleError(f"Error getting suggestions ({resp.status})")
            data = await resp.read()

            try:
                tree = Tree.fromstring(data.decode("utf-8"))
                for child in tree:
                    yield child[0].attrib.get("data", "")
            except Tree.ParseError:
                raise GoogleError(f"Suggestions returned malformed data")

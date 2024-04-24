# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 sardonicism-04
from random import choice
from typing import Optional

from aiohttp import ClientSession
from yarl import URL

from .objects import GoogleResponse, SearchResult

SEARCH_BASE = URL("https://www.googleapis.com/customsearch/v1")
GoogleError = type("GoogleError", (Exception,), {})


class Search:
    __slots__ = ("keys", "engine_id", "session")

    def __init__(
        self,
        *,
        keys: list[str],
        engine_id: str,
        session: Optional[ClientSession] = None,
    ):
        self.keys = keys
        self.engine_id = engine_id
        self.session = session or ClientSession()

    async def search(
        self,
        query: str,
        *,
        safesearch: bool = True,
        image: bool = False,
        results: int = 10,
    ) -> list[SearchResult]:
        params = dict(
            q=query, cx=self.engine_id, safe="active" if safesearch else "off"
        )
        if image:
            params.update(searchType="image")

        resp = await self._paginate_requests(
            SEARCH_BASE.with_query(**params), results=results
        )
        ret: list[SearchResult] = []
        for data in resp:
            ret.extend(data.results)
        return ret

    async def _paginate_requests(self, url: URL, *, results: int = 10):
        if results > 100:
            raise ValueError(
                "No more than 100 results may be requested at once"
            )

        # a copy of the key register to cycle through in case of too many reqs
        available_keys = self.keys[:]
        # randomly chosen key
        key = choice(available_keys)
        # index to start paginating at
        pagination_index = 1
        # all responses received thus far
        resps: list[GoogleResponse] = []

        while results > 0:
            async with self.session.get(
                url
                % {
                    "key": key,
                    "start": pagination_index,
                    "num": min(10, results),
                }
            ) as resp:
                data = await resp.json()

                if isinstance((error := data.get("error")), dict):
                    # if we get an "out of requests" error, then check if we
                    # still have more keys available
                    if (
                        error["code"] == 429
                        and error["status"] == "RESOURCE_EXHAUSTED"
                        and len(available_keys) > 1
                    ):
                        # if so, remove the dead key
                        available_keys.remove(key)
                        # replace it with a new one and try again
                        key = choice(available_keys)
                        continue
                    # otherwise give up
                    raise GoogleError(f"Error with search ({error['code']})")

                data_obj = GoogleResponse(data)
                resps.append(data_obj)
                if not data_obj.next_page:
                    # there are no results on upcoming pages, so don't waste
                    # requests, and return with what we've got
                    return resps

            results -= 10
            pagination_index += 10

        return resps

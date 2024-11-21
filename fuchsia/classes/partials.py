# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 vionya
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from discord import DMChannel, Object, User, abc

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine


class PartialUser(abc.Messageable, Object):
    """Represents a "partial" Discord user"""

    def __init__(self, *, state, id):
        self._state = state
        self.id = id

    def __repr__(self):
        return "<{0.__class__.__name__} id={0.id}>".format(self)

    @property
    def mention(self):
        return f"<@{self.id}>"

    async def fetch(self):
        """Fetches the partial user to a full User"""
        data = await self._state.http.get_user(self.id)
        return User(state=self._state, data=data)

    _get_channel: Callable[
        ..., Coroutine[Any, Any, DMChannel]
    ] = User._get_channel
    dm_channel = User.dm_channel
    create_dm = User.create_dm

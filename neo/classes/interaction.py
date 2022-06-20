# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from typing import Optional

import discord
from neo.classes.app_commands import get_ephemeral


class AutoEphemeralInteractionResponse(discord.InteractionResponse):
    async def defer(
        self, *, ephemeral: Optional[bool] = None, thinking: bool = False
    ) -> None:
        if ephemeral is None:
            _ephemeral = get_ephemeral(self._parent, self._parent.namespace)
        else:
            _ephemeral = ephemeral

        return await super().defer(ephemeral=_ephemeral, thinking=thinking)

    async def send_message(self, *args, **kwargs) -> None:

        if self._parent.type == discord.InteractionType.application_command:
            is_ephemeral = kwargs.pop("ephemeral", None) or getattr(
                self._parent.namespace, "private", True
            )

            if not self.is_done():
                await self.defer(ephemeral=is_ephemeral)

            await self._parent.followup.send(*args, ephemeral=is_ephemeral, **kwargs)
            return

        return await super().send_message(*args, **kwargs)

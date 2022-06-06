# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
import discord


class AutoEphemeralInteractionResponse(discord.InteractionResponse):
    async def send_message(self, *args, **kwargs) -> None:
        if (
            self._parent.type == discord.InteractionType.application_command
            and "ephemeral"
            not in kwargs  # kwargs take priority, so skip if it exists there
        ):
            return await super().send_message(
                *args,
                ephemeral=getattr(self._parent.namespace, "ephemeral", True),
                **kwargs
            )

        return await super().send_message(*args, **kwargs)

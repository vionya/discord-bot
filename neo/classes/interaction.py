from typing import cast

import discord
from neo import Neo


class AutoEphemeralInteractionResponse(discord.InteractionResponse):
    async def send_message(self, *args, **kwargs) -> None:
        if (
            self._parent.type == discord.InteractionType.application_command
            and "ephemeral" not in kwargs
        ):
            bot = cast(Neo, self._parent.client)
            user = self._parent.user

            default = True
            if user.id in bot.profiles:
                default = bot.profiles[user.id].default_ephemeral

            passed_option = getattr(self._parent.namespace, "ephemeral", None)
            ephemeral = default if passed_option is None else passed_option

            return await super().send_message(*args, ephemeral=ephemeral, **kwargs)

        return await super().send_message(*args, **kwargs)

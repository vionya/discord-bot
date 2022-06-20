# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
import logging

import discord

from neo.classes.app_commands import AutoEphemeralAppCommand
from neo.classes.formatters import format_exception
from neo.classes.interaction import AutoEphemeralInteractionResponse
from neo.tools import Patcher

logger = logging.getLogger("neo")

guild = Patcher(discord.Guild)
message = Patcher(discord.Message)
view = Patcher(discord.ui.View)
app_command = Patcher(discord.app_commands.commands)
interaction_response = Patcher(discord.interactions)


@guild.attribute()
async def fetch_member(self: discord.Guild, member_id, *, cache=False):
    data = await self._state.http.get_member(self.id, member_id)
    mem = discord.Member(data=data, state=self._state, guild=self)
    if cache:
        self._members[mem.id] = mem
    return mem


@message.attribute()
async def add_reaction(self, emoji):
    emoji = discord.message.convert_emoji_reaction(emoji)
    try:
        await self._state.http.add_reaction(self.channel.id, self.id, emoji)
    except discord.HTTPException as e:
        if e.code == 90001:
            return  # Ignore errors from trying to react to blocked users
        raise e  # If not 90001, re-raise


@view.attribute()
async def on_error(self, interaction, error, item):
    if isinstance(error, discord.Forbidden):
        if error.code == 50083:  # Tried to perform action in archived thread
            return
    logger.error(format_exception(error))


app_command.attribute(name="Command", value=AutoEphemeralAppCommand)
interaction_response.attribute(
    name="InteractionResponse", value=AutoEphemeralInteractionResponse
)


def patch_all() -> None:
    guild.patch()
    message.patch()
    view.patch()
    app_command.patch()
    interaction_response.patch()

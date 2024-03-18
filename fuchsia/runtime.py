# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from fuchsia.classes.app_commands import AutoEphemeralAppCommand
from fuchsia.classes.interaction import AutoEphemeralInteractionResponse
from fuchsia.tools import Patcher
from fuchsia.tools.formatters import format_exception

if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger("fuchsia")

guild = Patcher(discord.Guild)
message = Patcher(discord.Message)
view = Patcher(discord.ui.View)
app_command = Patcher(discord.app_commands.commands)
command = Patcher(discord.app_commands.commands.Command)
group = Patcher(discord.app_commands.commands.Group)
context_menu = Patcher(discord.app_commands.commands.ContextMenu)
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


@command.attribute(name="to_dict")
def command_to_dict(self) -> dict[str, Any]:
    option_type = (
        discord.AppCommandType.chat_input.value
        if self.parent is None
        else discord.AppCommandOptionType.subcommand.value
    )
    base: dict[str, Any] = {
        "name": self.name,
        "description": self.description,
        "type": option_type,
        "options": [param.to_dict() for param in self._params.values()],
        "integration_types": self.extras.get("integration_types", [0, 1]),
        "contexts": self.extras.get("contexts", [0, 1, 2]),
    }

    if self.parent is None:
        base["nsfw"] = self.nsfw
        base["dm_permission"] = not self.guild_only
        base["default_member_permissions"] = (
            None
            if self.default_permissions is None
            else self.default_permissions.value
        )

    return base


@group.attribute(name="to_dict")
def group_to_dict(self) -> dict[str, Any]:
    option_type = (
        1
        if self.parent is None
        else discord.AppCommandOptionType.subcommand_group.value
    )
    base: dict[str, Any] = {
        "name": self.name,
        "description": self.description,
        "type": option_type,
        "options": [child.to_dict() for child in self._children.values()],
        "integration_types": self.extras.get("integration_types", [0, 1]),
        "contexts": self.extras.get("contexts", [0, 1, 2]),
    }

    if self.parent is None:
        base["nsfw"] = self.nsfw
        base["dm_permission"] = not self.guild_only
        base["default_member_permissions"] = (
            None
            if self.default_permissions is None
            else self.default_permissions.value
        )

    return base


@context_menu.attribute(name="to_dict")
def ctx_menu_to_dict(self) -> dict[str, Any]:
    return {
        "name": self.name,
        "type": self.type.value,
        "dm_permission": not self.guild_only,
        "default_member_permissions": (
            None
            if self.default_permissions is None
            else self.default_permissions.value
        ),
        "nsfw": self.nsfw,
        "integration_types": self.extras.get("integration_types", [0, 1]),
        "contexts": self.extras.get("contexts", [0, 1, 2]),
    }


app_command.attribute(name="Command", value=AutoEphemeralAppCommand)
interaction_response.attribute(
    name="InteractionResponse", value=AutoEphemeralInteractionResponse
)


def patch_all() -> None:
    guild.patch()
    message.patch()
    view.patch()
    command.patch()
    group.patch()
    context_menu.patch()
    app_command.patch()
    interaction_response.patch()

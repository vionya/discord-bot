# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 vionya
from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands

import fuchsia
from fuchsia.tools import recursive_get_command

if TYPE_CHECKING:
    from fuchsia import Fuchsia


class DeprecationAlertButton(discord.ui.Button):
    def __init__(self, reason: str | bool):
        self.reason = reason if isinstance(reason, str) else None
        super().__init__(style=discord.ButtonStyle.red, label="!", row=4)

    async def callback(self, interaction: discord.Interaction):
        embed = fuchsia.Embed(
            title="This command has been deprecated, and will be removed in the future",
            description="Please become familiar with any alternatives that may exist."
            + (f"\n\nExtra Info: {self.reason}" if self.reason else ""),
        )
        await interaction.response.send_message(embeds=[embed], ephemeral=True)


class FuchsiaContext(commands.Context["Fuchsia"]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def send(self, *args, **kwargs) -> discord.Message:
        if self.interaction is not None:
            await self.interaction.response.send_message(*args, **kwargs)
            return await self.interaction.original_response()
        else:
            if self.command and (
                (
                    not self.interaction
                    and recursive_get_command(
                        self.bot.tree, self.command.qualified_name
                    )
                    is not None
                    and (deprecation := "Use the slash command variant")
                )
                or (deprecation := getattr(self.command.callback, "_deprecated", None))
            ):
                if "view" in kwargs:
                    kwargs["view"].add_item(DeprecationAlertButton(reason=deprecation))
                else:
                    kwargs["view"] = discord.ui.View()
                    kwargs["view"].add_item(DeprecationAlertButton(reason=deprecation))

            return await super().send(*args, **kwargs)

    async def send_confirmation(self):
        if not self.interaction:
            await self.message.add_reaction("\U00002611")
        else:
            await self.send("\U00002611")

# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 sardonicism-04
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord
from discord.ext import commands

import fuchsia
from fuchsia.tools import recursive_get_command

if TYPE_CHECKING:
    from fuchsia import Fuchsia


class PromptButton(discord.ui.Button):
    view: PromptActions

    def __init__(self, edited_content: str, value: bool, **kwargs):
        self.edited_content = edited_content
        self.value = value
        super().__init__(**kwargs)

    async def callback(self, interaction: discord.Interaction):
        embed = fuchsia.Embed(description=self.edited_content)
        [setattr(button, "disabled", True) for button in self.view.children]
        await interaction.response.edit_message(embed=embed, view=self.view)
        self.view.stop()
        self.view.value = self.value


class PromptActions(discord.ui.View):
    value: Optional[bool]

    def __init__(
        self,
        ctx,
        *,
        content_confirmed: str,
        content_cancelled: str,
        label_confirm: str,
        label_cancel: str,
    ):
        super().__init__()
        self.ctx = ctx
        for content, value, style, label in [
            (content_confirmed, True, discord.ButtonStyle.green, label_confirm),
            (content_cancelled, False, discord.ButtonStyle.red, label_cancel),
        ]:
            self.add_item(
                PromptButton(content, value, style=style, label=label)
            )
        self.value = None

    async def interaction_check(self, interaction):
        (predicates := []).append(
            interaction.user.id
            in (
                self.ctx.author.id,
                *self.ctx.bot.owner_ids,
                self.ctx.bot.owner_id,
            )
        )
        return all(predicates)


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

    async def prompt_user(
        self,
        prompt_message: str,
        *,
        content_confirmed: str = "Confirmed",
        content_cancelled: str = "Cancelled",
        label_confirm: str = "✓",
        label_cancel: str = "⨉",
    ):
        actions = PromptActions(
            self,
            content_confirmed=content_confirmed,
            content_cancelled=content_cancelled,
            label_confirm=label_confirm,
            label_cancel=label_cancel,
        )
        embed = fuchsia.Embed(description=prompt_message)
        await self.send(embed=embed, view=actions)
        await actions.wait()
        return actions.value

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
                or (
                    deprecation := getattr(
                        self.command.callback, "_deprecated", None
                    )
                )
            ):
                if "view" in kwargs:
                    kwargs["view"].add_item(
                        DeprecationAlertButton(reason=deprecation)
                    )
                else:
                    kwargs["view"] = discord.ui.View()
                    kwargs["view"].add_item(
                        DeprecationAlertButton(reason=deprecation)
                    )

            return await super().send(*args, **kwargs)

    async def send_confirmation(self):
        if not self.interaction:
            await self.message.add_reaction("\U00002611")
        else:
            await self.send("\U00002611")

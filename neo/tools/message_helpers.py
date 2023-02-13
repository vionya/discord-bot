# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
from __future__ import annotations

from typing import Optional

import discord

import neo


async def send_confirmation(
    interaction: discord.Interaction, *, ephemeral=None
):
    await interaction.response.send_message(
        "\U00002611", **{"ephemeral": True} if ephemeral is not None else {}
    )


class PromptButton(discord.ui.Button):
    view: PromptActions

    def __init__(self, edited_content: str, value: bool, **kwargs):
        self.edited_content = edited_content
        self.value = value
        super().__init__(**kwargs)

    async def callback(self, interaction: discord.Interaction):
        embed = neo.Embed(description=self.edited_content)
        [setattr(button, "disabled", True) for button in self.view.children]
        await interaction.response.edit_message(embed=embed, view=self.view)
        self.view.stop()
        self.view.value = self.value


class PromptActions(discord.ui.View):
    value: Optional[bool]

    def __init__(
        self,
        interaction: discord.Interaction,
        *,
        content_confirmed: str,
        content_cancelled: str,
        label_confirm: str,
        label_cancel: str,
    ):
        super().__init__()
        self.user = interaction.user
        for content, value, style, label in [
            (content_confirmed, True, discord.ButtonStyle.grey, label_confirm),
            (content_cancelled, False, discord.ButtonStyle.grey, label_cancel),
        ]:
            self.add_item(
                PromptButton(content, value, style=style, label=label)
            )
        self.value = None

    async def interaction_check(self, interaction):
        return interaction.user.id == self.user.id


async def prompt_user(
    interaction: discord.Interaction,
    prompt_message: str,
    *,
    content_confirmed: str = "Confirmed",
    content_cancelled: str = "Cancelled",
    label_confirm: str = "✓",
    label_cancel: str = "⨉",
):
    actions = PromptActions(
        interaction,
        content_confirmed=content_confirmed,
        content_cancelled=content_cancelled,
        label_confirm=label_confirm,
        label_cancel=label_cancel,
    )
    embed = neo.Embed(description=prompt_message)
    await interaction.response.send_message(embed=embed, view=actions)
    await actions.wait()
    return actions.value

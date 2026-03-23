# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2020-present vionya
from __future__ import annotations

from typing import Optional

import discord
from discord import ui

import fuchsia


def container_view(
    content: str, *, header: str | None = None, footer: str | None = None
) -> ui.LayoutView:
    """
    Creates a simple view with a CV2 container containing only ``content``

    :param content: What the container should contain
    :type content: ``str``
    """
    container = ui.Container()
    if header is not None:
        container.add_item(ui.TextDisplay(f"### {header}"))
    container.add_item(ui.TextDisplay(content))
    if footer is not None:
        container.add_item(ui.TextDisplay(f"-# {footer}"))
    return ui.LayoutView(timeout=0).add_item(container)


async def send_confirmation(
    interaction: discord.Interaction,
    *,
    ephemeral: bool | None = None,
    predicate: str | None = None,
):
    """
    Sends a confirmation message as a response to the specified interaction

    :param ephemeral: Whether the response should be ephemeral
    :type ephemeral: ``bool | None``

    :param predicate: The action that is being confirmed in the present perfect
                      tense
    :type predicate: ``str | None``
    """
    msg = "Success"
    if predicate:
        msg = f"Successfully {predicate}"

    content = f"\U00002714 {msg}!"
    container = ui.Container(ui.TextDisplay(content))
    view = ui.LayoutView().add_item(container)
    if ephemeral is not None:
        await interaction.response.send_message(view=view, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(view=view)


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


class PromptActions(ui.LayoutView):
    value: Optional[bool]

    def __init__(
        self,
        interaction: discord.Interaction,
        *,
        prompt: str,
        content_confirmed: str,
        content_cancelled: str,
        label_confirm: str,
        label_cancel: str,
    ):
        super().__init__()
        self.user = interaction.user

        row = ui.ActionRow()
        for content, value, style, label in [
            (content_confirmed, True, discord.ButtonStyle.green, label_confirm),
            (content_cancelled, False, discord.ButtonStyle.red, label_cancel),
        ]:
            row.add_item(PromptButton(content, value, style=style, label=label))
        container = ui.Container(ui.TextDisplay(prompt), row)
        self.add_item(container)
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
        prompt=prompt_message,
        content_confirmed=content_confirmed,
        content_cancelled=content_cancelled,
        label_confirm=label_confirm,
        label_cancel=label_cancel,
    )
    await interaction.response.send_message(view=actions)
    await actions.wait()
    return actions.value

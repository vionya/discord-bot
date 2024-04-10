# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 sardonicism-04
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands

from fuchsia.classes.exceptions import SilentFail

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from fuchsia import Fuchsia


async def owner_or_admin_predicate(interaction: discord.Interaction):
    assert interaction.command and isinstance(interaction.user, discord.Member)

    bot: Fuchsia = interaction.client  # type: ignore

    if not any(
        [
            interaction.user.guild_permissions.administrator,
            await bot.is_owner(interaction.user),
        ]
    ):
        raise app_commands.MissingPermissions(["administrator"])

    return True


def is_owner_or_administrator():
    return app_commands.check(owner_or_admin_predicate)


class CreateProfileView(discord.ui.View):
    edit_original_response: Callable[
        ..., Coroutine[Any, Any, discord.InteractionMessage]
    ]

    def __init__(
        self, invoker_id: int, original_interaction: discord.Interaction, **kwargs
    ):
        self.invoker_id = invoker_id
        self.original_interaction = original_interaction
        super().__init__(**kwargs)

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user.id == self.invoker_id

    async def on_timeout(self) -> None:
        self.create_profile_button.disabled = True
        await self.edit_original_response(view=self)

    @discord.ui.button(
        label="Create Profile & Run Command!", style=discord.ButtonStyle.primary
    )
    async def create_profile_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        bot: Fuchsia = interaction.client  # type: ignore
        if self.invoker_id in bot.profiles:
            return await interaction.response.send_message(
                "Looks like you already have a profile", ephemeral=True
            )
        await bot.add_profile(self.invoker_id)
        # swap out the interaction tokens
        interaction.data = self.original_interaction.data
        interaction.type = self.original_interaction.type
        # reinvoke the original interaction
        bot.tree._from_interaction(interaction)  # type: ignore
        # re-dispatch the interaction event
        bot.dispatch("interaction", interaction)
        button.disabled = True
        await self.edit_original_response(view=self)


async def is_registered_profile_predicate(interaction: discord.Interaction):
    assert interaction.command

    bot: Fuchsia = interaction.client  # type: ignore

    if interaction.user.id not in bot.profiles:
        view = CreateProfileView(interaction.user.id, interaction)
        msg = await interaction.response.send_message(
            "You don't have a profile! Create one now to run this command",
            view=view,
        )
        # backpatch the message onto the view
        view.edit_original_response = interaction.edit_original_response
        raise SilentFail("Missing a profile. Prompted to create one")
    return True


def is_registered_profile():
    """Verify the registration status of a user profile"""
    return app_commands.check(is_registered_profile_predicate)


def is_registered_guild_predicate(interaction: discord.Interaction):
    assert interaction.command

    guild = interaction.guild
    bot: Fuchsia = interaction.client  # type: ignore

    if not guild or guild.id not in bot.configs:
        raise app_commands.CommandInvokeError(
            interaction.command,
            AttributeError(
                "Looks like this server doesn't have an existing config entry. "
                "You can fix this with the `server create` command."
            ),
        )
    return True


def is_registered_guild():
    """Verify the registration status of a guild"""
    return app_commands.check(is_registered_guild_predicate)


def is_valid_starboard_env(interaction: discord.Interaction):
    assert interaction.command and interaction.guild

    bot: Fuchsia = interaction.client  # type: ignore
    config = bot.configs.get(interaction.guild.id)
    if not getattr(config, "starboard", False):
        raise app_commands.CommandInvokeError(
            interaction.command,
            AttributeError("Starboard is not enabled for this server!"),
        )

    return True

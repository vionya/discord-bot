# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

if TYPE_CHECKING:
    from neo import Neo


def is_owner_or_administrator():
    async def predicate(interaction: discord.Interaction):
        assert interaction.command and isinstance(interaction.user, discord.Member)

        bot: Neo = interaction.client  # type: ignore

        if not any(
            [
                interaction.user.guild_permissions.administrator,
                await bot.is_owner(interaction.user),
            ]
        ):
            raise app_commands.MissingPermissions(["administrator"])

        return True

    return app_commands.check(predicate)


def is_registered_profile_predicate(interaction: discord.Interaction):
    assert interaction.command

    bot: Neo = interaction.client  # type: ignore

    if interaction.user.id not in bot.profiles:
        raise app_commands.CommandInvokeError(
            interaction.command,
            AttributeError(
                "Looks like you don't have an existing profile! "
                "You can fix this with the `profile create` command."
            ),
        )
    return True


def is_registered_profile():
    """Verify the registration status of a user profile"""
    return app_commands.check(is_registered_profile_predicate)


def is_registered_guild_predicate(interaction: discord.Interaction):
    assert interaction.command

    guild = interaction.guild
    bot: Neo = interaction.client  # type: ignore

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


def valid_starboard_env():
    """Verify if an interaction environment is valid for a starboard"""

    def predicate(interaction: discord.Interaction):
        assert interaction.command and interaction.guild

        bot: Neo = interaction.client  # type: ignore
        config = bot.configs.get(interaction.guild.id)
        if not getattr(config, "starboard", False):
            raise app_commands.CommandInvokeError(
                interaction.command,
                AttributeError("Starboard is not enabled for this server!"),
            )

        return True

    return app_commands.check(predicate)

# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import discord
import neo
from discord import app_commands
from discord.ext import commands
from neo.classes.transformers import (
    bool_converter,
    timeout_converter,
    timezone_converter,
)
from neo.modules import ButtonsMenu
from neo.tools import convert_setting, instantiate, is_registered_profile, prompt_user
from neo.tools.checks import is_registered_profile_predicate

from .auxiliary.profile import ChangeSettingButton, ResetSettingButton

if TYPE_CHECKING:
    from neo.types.settings_mapping import SettingsMapping


SETTINGS_MAPPING: SettingsMapping = {
    "receive_highlights": {
        "transformer": bool_converter,
        "description": None,
    },
    "timezone": {"transformer": timezone_converter, "description": None},
    "hl_timeout": {"transformer": timeout_converter, "description": None},
    "default_ephemeral": {
        "transformer": bool_converter,
        "description": None,
    },
}


class Profile(neo.Addon, app_group=True):
    """neo phoenix's profile management module"""

    def __init__(self, bot: neo.Neo):
        self.bot = bot
        asyncio.create_task(self.__ainit__())

    async def __ainit__(self):
        await self.bot.wait_until_ready()

        for col_name in SETTINGS_MAPPING.keys():
            col_desc = await self.bot.db.fetchval(
                """
                SELECT get_column_description(
                    $1, 'profiles', $2
                )
                """,
                self.bot.cfg["database"]["database"],
                col_name,
            )

            SETTINGS_MAPPING[col_name]["description"] = col_desc

    async def set_option(
        self, interaction: discord.Interaction, setting: str, new_value: str
    ):
        value = await convert_setting(interaction, SETTINGS_MAPPING, setting, new_value)
        profile = self.bot.profiles[interaction.user.id]
        setattr(profile, setting, value)
        self.bot.broadcast("user_settings_update", interaction.user, profile)

    async def reset_option(self, interaction: discord.Interaction, setting: str):
        if not SETTINGS_MAPPING.get(setting):
            raise commands.BadArgument(
                "That's not a valid setting! " "Try `settings` for a list of settings!"
            )
        profile = self.bot.profiles[interaction.user.id]
        await profile.reset_attribute(setting)
        self.bot.broadcast("user_settings_update", interaction.user, profile)

    @instantiate
    class ProfileSettings(app_commands.Group, name="settings"):
        """Commands for managing profile settings"""

        addon: Profile

        @app_commands.command(name="list")
        @is_registered_profile()
        async def profile_settings_list(self, interaction: discord.Interaction):
            """Lists profile settings"""
            profile = self.addon.bot.profiles[interaction.user.id]
            embeds = []

            for setting, setting_info in SETTINGS_MAPPING.items():
                description = (setting_info["description"] or "").format(
                    getattr(profile, setting)
                )
                embed = neo.Embed(
                    title=f"Settings for {interaction.user}",
                    description=f"**Setting: `{setting}`**\n\n" + description,
                ).set_thumbnail(url=interaction.user.display_avatar)
                embeds.append(embed)

            menu = ButtonsMenu.from_embeds(embeds)

            menu.add_item(
                ChangeSettingButton(
                    addon=self.addon,
                    settings=SETTINGS_MAPPING,
                    label="Change this setting",
                    style=discord.ButtonStyle.primary,
                    row=0,
                )
            )
            menu.add_item(
                ResetSettingButton(
                    addon=self.addon,
                    settings=SETTINGS_MAPPING,
                    label="Reset this setting",
                    style=discord.ButtonStyle.danger,
                    row=0,
                )
            )

            await menu.start(interaction)

        @app_commands.command(name="set")
        @app_commands.describe(
            setting="The setting to set. More information can be found in the settings list",
            new_value="The new value to assign to this setting. More information"
            " can be found in the settings list",
        )
        @discord.app_commands.rename(new_value="new-value")
        @is_registered_profile()
        async def profile_settings_set(
            self, interaction: discord.Interaction, setting: str, new_value: str
        ):
            """
            Updates the value of a profile setting

            More information on the available settings and their functions is in the `settings` command
            """
            await self.addon.set_option(interaction, setting, new_value)
            await interaction.response.send_message(
                f"Setting `{setting}` has been changed!"
            )

        @app_commands.command(name="reset")
        @app_commands.describe(setting="The setting to reset")
        @is_registered_profile()
        async def profile_settings_reset(
            self, interaction: discord.Interaction, setting: str
        ):
            """
            Resets the value of a profile setting to its default

            Defaults can be found in the `settings` command
            """
            await self.addon.reset_option(interaction, setting)
            await interaction.response.send_message(
                f"Setting `{setting}` has been reset!"
            )

        @profile_settings_set.autocomplete("setting")
        @profile_settings_reset.autocomplete("setting")
        async def profile_settings_set_reset_autocomplete(
            self, interaction: discord.Interaction, current: str
        ):
            return [
                *map(
                    lambda k: discord.app_commands.Choice(name=k, value=k),
                    filter(lambda k: current in k, SETTINGS_MAPPING.keys()),
                )
            ]

    @app_commands.command(name="show")
    @discord.app_commands.describe(
        user="The user to view the profile for. Yourself if empty"
    )
    async def profile_show(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.User | discord.Member] = None,
    ):
        """Displays the neo profile of yourself, or a specified user."""
        user = user or interaction.user
        if user == interaction.user:
            is_registered_profile_predicate(interaction)

        profile = self.bot.profiles.get(user.id)
        if profile is None:
            raise AttributeError("This user doesn't have a neo profile!")

        assert self.bot.user
        embed = neo.Embed(
            description=(
                f"**<@{user.id}>'s neo profile**\n\n"
                f"**Created** <t:{int(profile.created_at.timestamp())}>"
            )
        ).set_thumbnail(
            url=self.bot.user.display_avatar
            if user != interaction.user
            else interaction.user.display_avatar
        )
        if getattr(profile, "timezone", None):
            embed.add_field(
                name="Time",
                value="**Timezone** {0}\n**Local Time** {1:%B %d, %Y %H:%M}".format(
                    profile.timezone, datetime.now(profile.timezone)
                ),
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="create")
    async def profile_create(self, interaction: discord.Interaction):
        """Creates your neo profile!"""
        if interaction.user.id in self.bot.profiles:
            raise RuntimeError("You already have a profile!")

        profile = await self.bot.add_profile(interaction.user.id)
        self.bot.broadcast("user_settings_update", interaction.user, profile)
        await interaction.response.send_message(
            "Successfully initialized your profile!"
        )

    @app_commands.command(name="delete")
    @is_registered_profile()
    async def profile_delete(self, interaction: discord.Interaction):
        """Permanently deletes your neo profile"""
        if (
            await prompt_user(
                interaction,
                "Are you sure you want to delete your profile?"
                "\nThis will delete your profile and all associated "
                "info (todos, highlights, etc), and **cannot** be undone.",
                label_confirm="I'm sure. Delete my profile.",
                label_cancel="Nevermind, don't delete my profile.",
                content_confirmed="Confirmed. Your profile is being deleted.",
            )
            is False
        ):
            return

        await self.bot.delete_profile(interaction.user.id)


async def setup(bot: neo.Neo):
    await bot.add_cog(Profile(bot))

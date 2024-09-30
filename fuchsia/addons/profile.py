# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 sardonicism-04
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

import discord
from discord import app_commands

import fuchsia
from fuchsia.modules import ButtonsMenu
from fuchsia.tools import (
    add_setting_autocomplete,
    convert_setting,
    singleton,
    is_registered_profile,
    prompt_user,
)
from fuchsia.tools.checks import is_registered_profile_predicate

from .auxiliary.profile import (
    SETTINGS_MAPPING,
    ChangeSettingButton,
    ResetSettingButton,
)


class Profile(fuchsia.Addon, app_group=True):
    """fuchsia's profile management module"""

    def __init__(self, bot: fuchsia.Fuchsia):
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
        value = await convert_setting(
            interaction, SETTINGS_MAPPING, setting, new_value
        )
        profile = self.bot.profiles[interaction.user.id]
        setattr(profile, setting, value)
        self.bot.broadcast("user_settings_update", interaction.user, profile)

    async def reset_option(
        self, interaction: discord.Interaction, setting: str
    ):
        if not SETTINGS_MAPPING.get(setting):
            raise NameError(
                "That's not a valid setting! "
                "Try `profile settings list` for a list of settings!"
            )
        profile = self.bot.profiles[interaction.user.id]
        await profile.reset_attribute(setting)
        self.bot.broadcast("user_settings_update", interaction.user, profile)

    @singleton
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
                embed = (
                    fuchsia.Embed(
                        title=setting_info.display_name,
                        description=description,
                    )
                    .set_thumbnail(url=interaction.user.display_avatar)
                    .set_author(
                        name=f"Settings for {interaction.user.display_name}",
                    )
                )
                embeds.append(embed)

            menu = ButtonsMenu.from_embeds(embeds)

            menu.add_item(
                ChangeSettingButton(
                    addon=self.addon,
                    label="Change this setting",
                    style=discord.ButtonStyle.primary,
                    row=0,
                )
            )
            menu.add_item(
                ResetSettingButton(
                    addon=self.addon,
                    label="Reset this setting",
                    style=discord.ButtonStyle.danger,
                    row=0,
                )
            )

            await menu.start(interaction)

        @add_setting_autocomplete(
            SETTINGS_MAPPING, setting_param="setting", value_param="new_value"
        )
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

            More information on the available settings and their functions[JOIN]
            is in the `settings` command
            """
            await self.addon.set_option(interaction, setting, new_value)
            await interaction.response.send_message(
                f"Setting `{SETTINGS_MAPPING[setting].display_name}` has been changed!"
            )

        @add_setting_autocomplete(SETTINGS_MAPPING, setting_param="setting")
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
                f"Setting `{SETTINGS_MAPPING[setting].display_name}` has been reset!"
            )

        # @profile_settings_set.autocomplete("setting")
        # @profile_settings_reset.autocomplete("setting")
        # async def profile_settings_set_reset_autocomplete(
        #     self, interaction: discord.Interaction, current: str
        # ):
        #     return generate_setting_mapping_autocomplete(SETTINGS_MAPPING, current)

    @app_commands.command(name="create")
    async def profile_create(self, interaction: discord.Interaction):
        """Creates your fuchsia profile!"""
        if interaction.user.id in self.bot.profiles:
            raise RuntimeError("You already have a profile!")

        await self.bot.add_profile(interaction.user.id)
        await interaction.response.send_message(
            "Successfully initialized your profile!"
        )

    @app_commands.command(name="delete")
    @is_registered_profile()
    async def profile_delete(self, interaction: discord.Interaction):
        """Permanently deletes your fuchsia profile"""
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


async def setup(bot: fuchsia.Fuchsia):
    await bot.add_cog(Profile(bot))

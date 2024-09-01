# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 sardonicism-04
from __future__ import annotations

import asyncio
from typing import Optional

import discord
from discord import app_commands

import fuchsia
from fuchsia.classes.transformers import command_transformer
from fuchsia.modules import ButtonsMenu
from fuchsia.tools import (
    add_setting_autocomplete,
    convert_setting,
    singleton,
    is_registered_guild,
    prompt_user,
)
from fuchsia.tools.checks import owner_or_admin_predicate
from fuchsia.types.commands import AnyCommand

from .auxiliary.server_settings import (
    SETTINGS_MAPPING,
    ChangeSettingButton,
    ResetSettingButton,
)


@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
@app_commands.allowed_installs(guilds=True, users=False)
class ServerConfig(
    fuchsia.Addon,
    name="Server Settings",
    app_group=True,
    group_name="server",
    group_description="Server configuration commands",
):
    """fuchsia's server config management module"""

    def __init__(self, bot: fuchsia.Fuchsia):
        self.bot = bot
        asyncio.create_task(self.__ainit__())

    async def __ainit__(self):
        await self.bot.wait_until_ready()

        for col_name in SETTINGS_MAPPING.keys():
            col_desc = await self.bot.db.fetchval(
                """
                SELECT get_column_description(
                    $1, 'guild_configs', $2
                )
                """,
                self.bot.cfg["database"]["database"],
                col_name,
            )

            SETTINGS_MAPPING[col_name]["description"] = col_desc

    async def set_option(
        self, interaction: discord.Interaction, setting: str, new_value: str
    ):
        assert interaction.guild

        value = await convert_setting(
            interaction, SETTINGS_MAPPING, setting, new_value
        )
        config = self.bot.configs[interaction.guild.id]
        setattr(config, setting, value)
        self.bot.broadcast("config_update", interaction.guild, config)

    async def reset_option(
        self, interaction: discord.Interaction, setting: str
    ):
        assert interaction.guild

        if not SETTINGS_MAPPING.get(setting):
            raise NameError(
                "That's not a valid setting! "
                "Try `server settings list` for a list of settings!"
            )
        config = self.bot.configs[interaction.guild.id]
        await config.reset_attribute(setting)
        self.bot.broadcast("config_update", interaction.guild, config)

    async def addon_interaction_check(
        self, interaction: discord.Interaction
    ) -> bool:
        return await owner_or_admin_predicate(interaction)

    @singleton
    class ServerSettings(app_commands.Group, name="settings"):
        """Commands for managing server settings"""

        addon: ServerConfig

        @app_commands.command(name="list")
        @is_registered_guild()
        async def server_settings_list(self, interaction: discord.Interaction):
            """Lists server settings"""
            # Guaranteed by addon check
            assert interaction.guild

            config = self.addon.bot.configs[interaction.guild.id]
            embeds = []

            for setting, setting_info in SETTINGS_MAPPING.items():
                description = (setting_info["description"] or "").format(
                    getattr(config, setting)
                )
                embed = (
                    fuchsia.Embed(
                        title=setting_info.display_name,
                        description=description,
                    )
                    .set_thumbnail(url=interaction.guild.icon)
                    .set_author(
                        name=f"Settings for {interaction.guild}",
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
        @app_commands.rename(new_value="new-value")
        @is_registered_guild()
        async def server_settings_set(
            self,
            interaction: discord.Interaction,
            setting: str,
            *,
            new_value: str,
        ):
            """
            Updates the value of a server setting

            More information on the available settings and their functions[JOIN]
            is in the `server` command
            """
            await self.addon.set_option(interaction, setting, new_value)
            await interaction.response.send_message(
                f"Setting {SETTINGS_MAPPING[setting].display_name} has been updated!"
            )

        @add_setting_autocomplete(SETTINGS_MAPPING, setting_param="setting")
        @app_commands.command(name="reset")
        @app_commands.describe(setting="The setting to reset")
        @is_registered_guild()
        async def server_settings_reset(
            self, interaction: discord.Interaction, setting: str
        ):
            """
            Resets the value of a server setting to its default

            Defaults can be found in the `server` command
            """
            await self.addon.reset_option(interaction, setting)
            await interaction.response.send_message(
                f"Setting {SETTINGS_MAPPING[setting].display_name} has been updated!"
            )

    @app_commands.command(name="create")
    async def server_create(self, interaction: discord.Interaction):
        """
        Creates a config entry for the server

        Run this command when fuchsia first joins your server, so you[JOIN]
        can start configuring your server
        """
        assert interaction.guild

        if interaction.guild.id in self.bot.configs:
            raise RuntimeError("Your server already has a config entry!")

        config = await self.bot.add_config(interaction.guild.id)
        self.bot.broadcast("config_update", interaction.guild, config)
        await interaction.response.send_message(
            "Successfully initialized your server's config!"
        )

    @app_commands.command(name="delete")
    @is_registered_guild()
    async def server_delete(self, interaction: discord.Interaction):
        """Permanently deletes this server's config"""
        assert interaction.guild

        if (
            await prompt_user(
                interaction,
                "Are you sure you want to delete the config?"
                "\nThis will delete your config and all associated "
                "data (starboard, stars, etc), and **cannot** be undone.",
                label_confirm="I'm sure. Delete my server config.",
                label_cancel="Nevermind, don't delete my server config.",
                content_confirmed="Confirmed. Your server config is being deleted.",
            )
            is False
        ):
            return

        await self.bot.delete_config(interaction.guild.id)


async def setup(bot: fuchsia.Fuchsia):
    await bot.add_cog(ServerConfig(bot))

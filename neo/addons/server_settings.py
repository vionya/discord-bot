# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
from __future__ import annotations

import asyncio
from typing import Optional

import discord
from discord import app_commands

import neo
from neo.classes.transformers import command_transformer
from neo.modules import ButtonsMenu
from neo.tools import (
    add_setting_autocomplete,
    convert_setting,
    instantiate,
    is_registered_guild,
    prompt_user,
    send_confirmation,
)
from neo.tools.checks import owner_or_admin_predicate
from neo.types.commands import AnyCommand

from .auxiliary.server_settings import (
    SETTINGS_MAPPING,
    ChangeSettingButton,
    ResetSettingButton,
)


@app_commands.guild_only()
class ServerConfig(
    neo.Addon,
    name="Server Settings",
    app_group=True,
    group_name="server",
    group_description="Server configuration commands",
):
    """neo phoenix's server config management module"""

    def __init__(self, bot: neo.Neo):
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

    @instantiate
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
                embed = neo.Embed(
                    title=f"Settings for {interaction.guild}",
                    description=f"**Setting: `{setting_info.display_name}`**\n\n"
                    + description,
                ).set_thumbnail(url=interaction.guild.icon)
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

        Run this command when neo phoenix first joins your server, so you[JOIN]
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

    @app_commands.command(name="ignore")
    @app_commands.describe(channel="The channel to ignore")
    @is_registered_guild()
    async def server_ignore_channel(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ):
        """
        Ignores a channel. Run without arguments to view ignored channels

        Any attempts to run a command in an ignored channel will be[JOIN]
        ignored, *unless they are executed by someone with administrator*[JOIN]
        *permissions*
        """
        assert interaction.guild

        config = self.bot.configs[interaction.guild.id]
        if not channel:
            menu = ButtonsMenu.from_iterable(
                [*map(lambda id: f"`{id}` [<#{id}>]", config.disabled_channels)]
                or ["No ignored channels"],
                per_page=10,
                use_embed=True,
                template_embed=neo.Embed().set_author(
                    name=f"Ignored channels for {interaction.guild}",
                    icon_url=interaction.guild.icon,
                ),
            )
            await menu.start(interaction)
            return

        (
            channel_ids := {
                *config.disabled_channels,
            }
        ).add(channel.id)
        config.disabled_channels = [*channel_ids]
        await send_confirmation(
            interaction, predicate=f"ignored {channel.mention}"
        )

    @app_commands.command(name="unignore")
    @app_commands.describe(channel="The channel to unignore")
    @is_registered_guild()
    async def server_unignore_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        """Unignores a channel for command responses"""
        assert interaction.guild

        config = self.bot.configs[interaction.guild.id]
        (
            channel_ids := {
                *config.disabled_channels,
            }
        ).discard(channel.id)

        config.disabled_channels = [*channel_ids]
        await send_confirmation(
            interaction, predicate=f"unignored {channel.mention}"
        )

    @app_commands.command(name="disable")
    @app_commands.describe(command="The command to disable")
    @is_registered_guild()
    async def server_disable_command(
        self,
        interaction: discord.Interaction,
        *,
        command: Optional[
            app_commands.Transform[AnyCommand, command_transformer]
        ],
    ):
        """
        Disables a command in the server. Run without arguments to view [JOIN]
        disabled commands

        When disabling group commands and subcommands, behavior is as[JOIN]
        follows:
        - Disabling a group command will disable the group and all its[JOIN]
        subcommands
        - Disabling a subcommand will disable only the subcommand, not the[JOIN]
        entire group

        Any attempts to run a disabled command will be ignored, *unless*[JOIN]
        executed by someone with administrator permissions*
        """
        assert interaction.guild

        config = self.bot.configs[interaction.guild.id]
        if not command:
            menu = ButtonsMenu.from_iterable(
                [*map(lambda cmd: f"`{cmd}`", config.disabled_commands)]
                or ["No disabled commands"],
                per_page=10,
                use_embed=True,
                template_embed=neo.Embed().set_author(
                    name=f"Disabled commands for {interaction.guild}",
                    icon_url=interaction.guild.icon,
                ),
            )
            await menu.start(interaction)
            return

        (
            commands := {
                *config.disabled_commands,
            }
        ).add(command.qualified_name)
        config.disabled_commands = [*commands]
        await send_confirmation(
            interaction, predicate=f"disabled {command.name}"
        )

    @app_commands.command(name="enable")
    @app_commands.describe(command="The command to re-enable")
    @is_registered_guild()
    async def server_enable_command(
        self,
        interaction: discord.Interaction,
        *,
        command: app_commands.Transform[AnyCommand, command_transformer],
    ):
        """Re-enables a disabled command"""
        assert interaction.guild

        config = self.bot.configs[interaction.guild.id]
        (
            commands := {
                *config.disabled_commands,
            }
        ).discard(command.qualified_name)

        config.disabled_commands = [*commands]
        await send_confirmation(
            interaction, predicate=f"enabled {command.name}"
        )

    @server_enable_command.autocomplete("command")
    async def server_enable_command_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        if (
            not interaction.guild
            or interaction.guild.id not in self.bot.configs
        ):
            return []

        config = self.bot.configs[interaction.guild.id]
        return [
            app_commands.Choice(name=k, value=k)
            for k in config.disabled_commands
            if current in k
        ][:25]


async def setup(bot: neo.Neo):
    await bot.add_cog(ServerConfig(bot))

# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

import discord
import neo
from discord.ext import commands
from neo.classes.converters import command_converter
from neo.modules import ButtonsMenu
from neo.tools import convert_setting, is_registered_guild

from .auxiliary.server_settings import ChangeSettingButton, ResetSettingButton

if TYPE_CHECKING:
    from neo.classes.context import NeoContext
    from neo.types.settings_mapping import SettingsMapping

SETTINGS_MAPPING: SettingsMapping = {
    "prefix": {
        "converter": str,
        "description": None
    },
    "starboard": {
        "converter": commands.converter._convert_to_bool,
        "description": None
    }
}


class ServerSettings(neo.Addon):
    """
    neo phoenix's server config management module

    Create a server config to use features such as starboards and custom prefixes!
    """

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
                col_name
            )

            SETTINGS_MAPPING[col_name]["description"] = col_desc

    async def cog_check(self, ctx: NeoContext):
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            raise commands.NoPrivateMessage()

        if not any([
            ctx.author.guild_permissions.administrator,
            await self.bot.is_owner(ctx.author)
        ]):
            raise commands.MissingPermissions(["administrator"])

        return True

    @commands.hybrid_group(name="serversettings", aliases=["server"])
    async def server_settings(self, ctx: NeoContext):
        """Group command for managing server settings"""

    @server_settings.command(name="list")
    async def server_settings_list(self, ctx: NeoContext):
        """Lists server settings"""
        # Guaranteed by cog check
        assert ctx.guild

        await is_registered_guild().predicate(ctx)
        config = self.bot.configs[ctx.guild.id]
        embeds = []

        for setting, setting_info in SETTINGS_MAPPING.items():
            description = (setting_info["description"] or "").format(
                getattr(config, setting)
            )
            embed = neo.Embed(
                title=f"Settings for {ctx.guild}",
                description=f"**Setting: `{setting}`**\n\n" + description
            ).set_thumbnail(url=ctx.guild.icon)
            embeds.append(embed)

        menu = ButtonsMenu.from_embeds(embeds)
        menu.add_item(ChangeSettingButton(
            ctx=ctx,
            addon=self,
            settings=SETTINGS_MAPPING,
            label="Change this setting",
            style=discord.ButtonStyle.primary,
            row=0
        ))
        menu.add_item(ResetSettingButton(
            ctx=ctx,
            addon=self,
            settings=SETTINGS_MAPPING,
            label="Reset this setting",
            style=discord.ButtonStyle.danger,
            row=0
        ))

        await menu.start(ctx)

    async def set_option(self, ctx: NeoContext, setting: str, new_value: str):
        assert ctx.guild

        value = await convert_setting(ctx, SETTINGS_MAPPING, setting, new_value)
        config = self.bot.configs[ctx.guild.id]
        setattr(config, setting, value)
        self.bot.broadcast("config_update", ctx.guild, config)

    async def reset_option(self, ctx: NeoContext, setting: str):
        assert ctx.guild

        if not SETTINGS_MAPPING.get(setting):
            raise commands.BadArgument(
                "That's not a valid setting! "
                "Try `server` for a list of settings!"
            )
        config = self.bot.configs[ctx.guild.id]
        await config.reset_attribute(setting)
        self.bot.broadcast("config_update", ctx.guild, config)

    @server_settings.command(name="set")
    @discord.app_commands.describe(
        setting="The setting to set. More information can be found in the settings list",
        new_value="The new value to assign to this setting. More information"
        " can be found in the settings list"
    )
    @is_registered_guild()
    async def server_settings_set(self, ctx: NeoContext, setting: str, *, new_value: str):
        """
        Updates the value of a server setting

        More information on the available settings and
        their functions is in the `server` command
        """
        await self.set_option(ctx, setting, new_value)
        await ctx.send(f"Setting `{setting}` has been changed!")

    @server_settings.command(name="reset")
    @discord.app_commands.describe(setting="The setting to reset")
    @is_registered_guild()
    async def server_settings_reset(self, ctx: NeoContext, setting: str):
        """
        Resets the value of a server setting to its default

        Defaults can be found in the `server` command
        """
        await self.reset_option(ctx, setting)
        await ctx.send(f"Setting `{setting}` has been reset!")

    @server_settings_set.autocomplete("setting")
    @server_settings_reset.autocomplete("setting")
    async def server_settings_set_reset_autocomplete(self, interaction: discord.Interaction, current: str):
        return [*map(lambda k: discord.app_commands.Choice(name=k, value=k),
                     filter(lambda k: current in k, SETTINGS_MAPPING.keys()))]

    @server_settings.command(name="create")
    async def server_settings_create(self, ctx: NeoContext):
        """
        Creates a config entry for the server

        Run this command when neo phoenix first
        joins your server, so you can start
        configuring your server
        """
        assert ctx.guild

        if ctx.guild.id in self.bot.configs:
            raise RuntimeError("Your server already has a config entry!")

        config = await self.bot.add_config(ctx.guild.id)
        self.bot.broadcast("config_update", ctx.guild, config)
        await ctx.send("Successfully initialized your server's config!")

    @server_settings.command(name="delete")
    @is_registered_guild()
    async def server_settings_delete(self, ctx: NeoContext):
        """Permanently deletes this server's config"""
        assert ctx.guild

        if await ctx.prompt_user(
            "Are you sure you want to delete the config?"
            "\nThis will delete your config and all associated "
            "data (starboard, stars, etc), and **cannot** be undone.",
            label_confirm="I'm sure. Delete my server config.",
            label_cancel="Nevermind, don't delete my server config.",
            content_confirmed="Confirmed. Your server config is being deleted."
        ) is False:
            return

        await self.bot.delete_config(ctx.guild.id)

    @server_settings.command(name="ignore")
    @is_registered_guild()
    async def server_settings_ignore_channel(
            self, ctx: NeoContext, channel: Optional[discord.TextChannel] = None):
        """
        Ignores a channel. Run without arguments to view ignored channels

        Any attempts to run a command in an ignored
        channel will be ignored, *unless they are*
        *executed by someone with administrator*
        *permissions*
        """
        assert ctx.guild

        config = self.bot.configs[ctx.guild.id]
        if not channel:
            menu = ButtonsMenu.from_iterable(
                [*map(lambda id: f"`{id}` [<#{id}>]", config.disabled_channels)]
                or ["No ignored channels"],
                per_page=10,
                use_embed=True,
                template_embed=neo.Embed().set_author(
                    name=f"Ignored channels for {ctx.guild}",
                    icon_url=ctx.guild.icon
                )
            )
            await menu.start(ctx)
            return

        (channel_ids := {*config.disabled_channels, }).add(channel.id)
        config.disabled_channels = [*channel_ids]
        await ctx.send_confirmation()

    @server_settings.command(name="unignore")
    @is_registered_guild()
    async def server_settings_unignore_channel(
            self, ctx: NeoContext, channel: discord.TextChannel):
        """Unignores a channel for command responses"""
        assert ctx.guild

        config = self.bot.configs[ctx.guild.id]
        (channel_ids := {*config.disabled_channels, }).discard(channel.id)

        config.disabled_channels = [*channel_ids]
        await ctx.send_confirmation()

    @server_settings.command(name="disable")
    @is_registered_guild()
    async def server_settings_disable_command(
            self, ctx: NeoContext, *, command: Optional[command_converter] = None):
        """
        Disables a command in the server. Run without arguments to view
        disabled commands

        When disabling group commands and subcommands,
        behavior is as follows:
        - Disabling a group command will disable the group
        and all its subcommands
        - Disabling a subcommand will disable only the
        subcommand, not the entire group

        Any attempts to run a disabled command
        will be ignored, *unless executed by*
        *someone with administrator permissions*
        """
        assert ctx.guild

        config = self.bot.configs[ctx.guild.id]
        if not command:
            menu = ButtonsMenu.from_iterable(
                [*map(lambda cmd: f"`{cmd}`", config.disabled_commands)]
                or ["No disabled commands"],
                per_page=10,
                use_embed=True,
                template_embed=neo.Embed().set_author(
                    name=f"Disabled commands for {ctx.guild}",
                    icon_url=ctx.guild.icon
                )
            )
            await menu.start(ctx)
            return

        (commands := {*config.disabled_commands, }).add(str(command))
        config.disabled_commands = [*commands]
        await ctx.send_confirmation()

    @server_settings.command(name="reenable", aliases=["enable"])
    @is_registered_guild()
    async def server_settings_reenable_command(self, ctx: NeoContext, *, command: command_converter):
        """Re-enables a disabled command"""
        assert ctx.guild

        config = self.bot.configs[ctx.guild.id]
        (commands := {*config.disabled_commands, }).discard(str(command))

        config.disabled_commands = [*commands]
        await ctx.send_confirmation()


async def setup(bot: neo.Neo):
    await bot.add_cog(ServerSettings(bot))

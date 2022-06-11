# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

import asyncio
import inspect
import logging
import sys
import time
from typing import TYPE_CHECKING, Any

import discord
from aiohttp import ClientSession
from asyncpg import create_pool
from discord.ext import commands

from .classes import Embed, containers, context, formatters, help_command, partials
from .modules import *  # noqa: F403
from .tools import *  # noqa: F403
from .tools import recursive_getattr

if TYPE_CHECKING:
    from collections.abc import Coroutine, Mapping

    from asyncpg import Pool

    from .modules.addon.addon import Addon
    from .types.config import NeoConfig


__version__ = "0.15.1"

log = logging.getLogger(__name__)
intents = discord.Intents(
    **dict.fromkeys(["messages", "guilds", "guild_reactions", "message_content"], True)
)


class Neo(commands.Bot):
    db: Pool
    session: ClientSession
    cogs: Mapping[str, Addon]

    def __init__(self, config: NeoConfig, **kwargs):
        self.cfg = config
        self.boot_time = int(time.time())
        self.profiles: dict[int, containers.NeoUser] = {}
        self.configs: dict[int, containers.NeoGuildConfig] = {}

        kwargs["command_prefix"] = self.get_prefix
        kwargs["activity"] = discord.Activity(
            name=config["bot"]["activity_name"],
            type=discord.ActivityType[config["bot"]["activity_type"]],
            url="https://twitch.tv/#",  # for spoofing Discord when activity type is streaming
        )
        kwargs["status"] = discord.Status[config["bot"]["status"]]
        kwargs["allowed_mentions"] = discord.AllowedMentions.none()
        kwargs["help_command"] = help_command.NeoHelpCommand()
        kwargs["intents"] = intents
        kwargs["case_insensitive"] = True

        super().__init__(**kwargs)

        self.cooldown = commands.CooldownMapping.from_cooldown(
            2, 4, commands.BucketType.user
        )
        self.add_check(self.global_cooldown, call_once=True)  # Register global cooldown
        self.add_check(
            self.channel_check, call_once=True
        )  # Register channel disabled check
        self.add_check(self.guild_disabled_check)  # Register command disabled check

        self.tree.on_error = self.general_error_handler  # type: ignore
        self.tree.interaction_check = self.tree_interaction_check

        self.on_command_error = self.general_error_handler  # type: ignore

        self._async_ready = asyncio.Event()
        asyncio.create_task(self.__ainit__())

    async def __ainit__(self) -> None:
        self.session = ClientSession()

        pool = await create_pool(**self.cfg["database"])
        if not pool:
            raise RuntimeError("Failed to create database connection")
        self.db = pool

        # Load initial profiles from database
        for record in await self.db.fetch("SELECT * FROM profiles"):
            await self.add_profile(record["user_id"], record=record)

        # Load initial guild configurations from database
        for record in await self.db.fetch("SELECT * FROM guild_configs"):
            await self.add_config(record["guild_id"], record=record)

        self._async_ready.set()
        await self.verify_configs()

    async def wait_until_ready(self):
        await self._async_ready.wait()
        return await super().wait_until_ready()

    async def verify_configs(self) -> None:
        """Purges configs where the bot is no longer in the corresponding guild"""
        await self.wait_until_ready()

        for guild_id in self.configs.copy():
            if not self.get_guild(guild_id):
                await self.delete_config(guild_id)

    async def add_profile(self, user_id, *, record=None):
        if not record:
            record = await self.db.fetchrow(
                """
                INSERT INTO profiles (
                    user_id
                ) VALUES (
                    $1
                ) RETURNING *
                """,
                user_id,
            )
        profile = containers.NeoUser(pool=self.db, **record)
        self.profiles[user_id] = profile
        return profile

    async def delete_profile(self, user_id: int):
        self.profiles.pop(user_id, None)
        await self.db.execute(
            """
            DELETE FROM
                profiles
            WHERE
                user_id=$1
            """,
            user_id,
        )
        self.broadcast("profile_delete", user_id)

    async def add_config(self, guild_id: int, *, record=None):
        if not record:
            record = await self.db.fetchrow(
                """
                INSERT INTO guild_configs (
                    guild_id
                ) VALUES (
                    $1
                ) RETURNING *
                """,
                guild_id,
            )
        config = containers.NeoGuildConfig(pool=self.db, **record)
        self.configs[guild_id] = config
        return config

    async def delete_config(self, guild_id: int):
        self.configs.pop(guild_id, None)
        await self.db.execute(
            """
            DELETE FROM
                guild_configs
            WHERE
                guild_id=$1
            """,
            guild_id,
        )
        self.broadcast("config_delete", guild_id)

    async def start(self):
        for addon in self.cfg["addons"]:
            await self.load_extension(addon)

        async with self:
            await super().start(self.cfg["bot"]["token"])

    async def close(self):
        await self.session.close()
        await asyncio.wait_for(self.db.close(), 5)

        await super().close()

    async def on_ready(self):
        log.info(f"{self.user} has received ready event")
        if self.cfg["bot"]["sync_app_commands"]:
            await self.tree.sync()
            log.info("Synchronized command tree")

    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.content != before.content:
            await self.process_commands(after)

    async def get_prefix(self, message: discord.Message) -> list[str]:
        if message.guild:
            return commands.when_mentioned_or(
                getattr(
                    self.configs.get(message.guild.id),
                    "prefix",
                    self.cfg["bot"]["prefix"],
                )
            )(self, message)

        return commands.when_mentioned_or(self.cfg["bot"]["prefix"])(self, message)

    async def on_error(self, *args, **kwargs):
        log.error("\n" + formatters.format_exception(sys.exc_info()))

    async def general_error_handler(
        self,
        origin: context.NeoContext | discord.Interaction,
        exception: discord.DiscordException,
    ):
        async def send(content: str):
            if isinstance(origin, context.NeoContext):
                await origin.send(content, ephemeral=True)
            elif isinstance(origin, discord.Interaction):
                await origin.response.send_message(content, ephemeral=True)

        original_error: BaseException = recursive_getattr(
            exception, "original", exception
        )

        if isinstance(original_error, AssertionError):
            return await send(
                "Something that shouldn't have gone wrong went wrong. Please report this!"
            )

        if origin.__class__.__name__ in self.cfg["bot"]["ignored_exceptions"]:
            if not isinstance(origin, discord.Interaction):
                return

        try:
            await send(str(original_error))
        except discord.Forbidden:
            pass

        log.error(
            f"In command: {getattr(origin.command, 'qualified_name', '[unknown command]')}\n"  # type: ignore
            + formatters.format_exception(original_error)
        )

    async def get_context(
        self, message: discord.Message | discord.Interaction, *, cls=context.NeoContext
    ):
        return await super().get_context(message, cls=cls)

    # TODO: Remove this if/when it's properly supported by discord.py
    def add_command(self, command, /):
        if isinstance(command, commands.HybridCommand | commands.HybridGroup):
            if command.app_command is not None and all(
                [
                    command.with_app_command,
                    command.cog is None
                    or not command.cog.__cog_is_app_commands_group__,
                ]
            ):
                self.tree.add_command(command.app_command)
            if getattr(command, "with_command", True):
                commands.GroupMixin.add_command(self, command)
            return
        else:
            super().add_command(command)

    def get_user(self, id, *, as_partial=False):
        user = self._connection.get_user(id)
        if as_partial or not user:
            user = partials.PartialUser(state=self._connection, id=id)
        return user

    async def on_guild_remove(self, guild: discord.Guild):
        await self.delete_config(guild.id)

    async def tree_interaction_check(self, interaction: discord.Interaction):
        # Intercept app commands
        if (
            interaction.type == discord.InteractionType.application_command
            and interaction.command
        ):
            ctx = await context.NeoContext.from_interaction(interaction)
            # Get global checks
            checks = [*self._checks, *self._check_once]

            if len(checks) == 0:
                return True

            # Verify the app commands against the global checks
            try:
                return await discord.utils.async_all(f(ctx) for f in checks)  # type: ignore
            except Exception as e:
                # If it fails, then re-raise it wrapped in an invoke error
                raise discord.app_commands.CommandInvokeError(interaction.command, e)

        return True

    async def global_cooldown(self, ctx: context.NeoContext):
        if await self.is_owner(ctx.author):
            return True

        retry_after = self.cooldown.update_rate_limit(ctx.message)
        actual_cooldown = self.cooldown._cooldown
        if not actual_cooldown:
            return True

        if retry_after:
            raise commands.CommandOnCooldown(
                actual_cooldown, retry_after, commands.BucketType.user
            )
        return True

    async def channel_check(self, ctx: context.NeoContext):
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return True

        predicates = [
            getattr(ctx.guild, "id", None) not in self.configs,
            await self.is_owner(ctx.author),
        ]

        if hasattr(ctx.channel, "permissions_for"):
            predicates.append(ctx.channel.permissions_for(ctx.author).administrator)

        if any(predicates):
            return True

        if ctx.channel.id in self.configs[ctx.guild.id].disabled_channels:
            raise commands.DisabledCommand("Commands are disabled in this channel.")
        return True

    async def guild_disabled_check(self, ctx: context.NeoContext):
        if (
            not ctx.guild
            or not isinstance(ctx.author, discord.Member)
            or not ctx.command
        ):
            return True

        predicates = [
            getattr(ctx.guild, "id", None) not in self.configs,
            await self.is_owner(ctx.author),
        ]

        if hasattr(ctx.channel, "permissions_for"):
            predicates.append(ctx.channel.permissions_for(ctx.author).administrator)

        if any(predicates):
            return True

        disabled = self.configs[ctx.guild.id].disabled_commands
        if str(ctx.command.qualified_name) in disabled or (
            str(ctx.command.root_parent.name) in disabled  # type: ignore
            if getattr(ctx.command, "root_parent", None) is not None
            else False
        ):
            raise commands.DisabledCommand("This command is disabled in this server.")
        return True

    # discord.py's `Client.dispatch` API is both private and *volatile*.
    # This serves as a similar implementation that will not change in the future.

    def broadcast(self, event: str, *args, **kwargs):
        coros: list[Coroutine[None, None, Any]] = []
        for addon in self.cogs.values():
            if event in addon.__receivers__:
                receiver = addon.__receivers__[event]
                if not inspect.iscoroutinefunction(receiver):
                    receiver(addon, *args, **kwargs)
                else:
                    coros.append(receiver(addon, *args, **kwargs))

        async def run_coros():
            await asyncio.gather(*coros)

        asyncio.create_task(run_coros())

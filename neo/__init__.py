# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

import asyncio
import inspect
import logging
import sys
import time
from typing import TYPE_CHECKING

import discord
from aiohttp import ClientSession
from asyncpg import create_pool
from discord.ext import commands

from .classes import Embed, containers, context, exceptions, help_command, partials
from .modules import *  # noqa: F403
from .tools import *  # noqa: F403
from .tools import formatters, recursive_getattr

if TYPE_CHECKING:
    from collections.abc import Awaitable, Mapping

    from asyncpg import Pool

    from .modules.addon.addon import Addon
    from .types.config import NeoConfig


__version__ = "1.3.1"

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

        kwargs["command_prefix"] = self.cfg["bot"]["prefix"]
        kwargs["activity"] = discord.Activity(
            name=config["bot"]["activity_name"].format(version=__version__),
            type=discord.ActivityType[config["bot"]["activity_type"]],
            url="https://twitch.tv/#",  # for spoofing Discord when activity type is streaming
        )
        kwargs["status"] = discord.Status[config["bot"]["status"]]
        kwargs["allowed_mentions"] = discord.AllowedMentions.none()
        kwargs["help_command"] = None
        kwargs["intents"] = intents
        kwargs["case_insensitive"] = True

        super().__init__(**kwargs)

        self.tree.on_error = self.general_error_handler  # type: ignore
        self.tree.interaction_check = self.tree_interaction_check

        self.on_command_error = self.general_error_handler  # type: ignore

        self.tree.add_command(help_command.AppHelpCommand(self))

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
            exception, "__cause__"
        ) or recursive_getattr(exception, "original", exception)

        level = logging.INFO
        try:
            if isinstance(original_error, AssertionError):
                level = logging.ERROR
                return await send("Something weird happened. Please report this!")

            if (
                original_error.__class__.__name__
                in self.cfg["bot"]["ignored_exceptions"]
            ):
                level = logging.DEBUG
                if not isinstance(origin, discord.Interaction):
                    # In the event of interactions, exceptions can be displayed ephemerally
                    return

            await send(str(original_error))

        except discord.Forbidden:
            pass

        finally:
            log.log(
                level,
                f"In command: {getattr(origin.command, 'qualified_name', '[unknown command]')}\n"  # type: ignore
                + formatters.format_exception(original_error),
            )

    async def get_context(
        self, message: discord.Message | discord.Interaction, *, cls=context.NeoContext
    ):
        return await super().get_context(message, cls=cls)

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
            # Verify the interaction against the checks
            # Hierarchy prioritizes channel check first since it will overrule anyways
            try:
                await self.channel_check(interaction)
                await self.guild_disabled_check(interaction)
            except Exception as e:
                # If it fails, then re-raise it wrapped in an invoke error
                raise discord.app_commands.CommandInvokeError(
                    interaction.command, e
                ) from e

        return True

    # TODO: Remove this in favor of Discord's built-in permissions system?
    async def channel_check(self, interaction: discord.Interaction):
        # Only relevant in guilds
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return True

        predicates = [
            # If the guild ID has no associated config, this check is irrelevant
            interaction.guild.id not in self.configs,
            # Bypasses
            await self.is_owner(interaction.user),
            interaction.user.guild_permissions.administrator,
        ]

        if any(predicates):
            return True

        elif (
            interaction.channel_id
            in self.configs[interaction.guild.id].disabled_channels
        ):
            # If the channel is in the list of disabled IDs, the command
            # can't be executed
            raise exceptions.DisabledChannel()

        return True

    # TODO: Remove in favor of built-in Discord permissions as well?
    async def guild_disabled_check(self, interaction: discord.Interaction):
        if (
            not interaction.guild
            or not isinstance(interaction.user, discord.Member)
            or not isinstance(interaction.command, discord.app_commands.Command)
        ):
            return True

        predicates = [
            interaction.guild.id not in self.configs,
            await self.is_owner(interaction.user),
            interaction.user.guild_permissions.administrator,
        ]

        if any(predicates):
            return True

        disabled = self.configs[interaction.guild.id].disabled_commands
        if (
            interaction.command.qualified_name in disabled
            or getattr(interaction.command.root_parent, "name", "") in disabled
        ):
            raise exceptions.DisabledCommand(interaction.command.qualified_name)

    # discord.py's `Client.dispatch` API is both private and *volatile*.
    # This serves as a similar implementation that will not change in the future.

    def broadcast(self, event: str, *args, **kwargs):
        coros: list[Awaitable[None]] = []
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

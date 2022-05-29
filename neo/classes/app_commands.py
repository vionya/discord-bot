# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional, ParamSpec, TypeVar, Union

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from neo.classes.context import NeoContext
    from discord.app_commands import Group
    from discord.app_commands.commands import CommandCallback

T = TypeVar("T")
P = ParamSpec("P")

GroupT = TypeVar("GroupT", bound=Union["Group", "commands.Cog"])


class AutoEphemeralAppCommand(discord.app_commands.Command[GroupT, P, T]):
    def __init__(
        self,
        *,
        name: str,
        description: str,
        callback: CommandCallback[GroupT, P, T],
        parent: Optional[Group] = None,
        guild_ids: Optional[list[int]] = None,
        nsfw: bool = False,
    ):
        super().__init__(
            name=name,
            description=description,
            callback=callback,
            parent=parent,
            guild_ids=guild_ids,
            nsfw=nsfw,
        )

        # Inject an `ephemeral` parameter to every hybrid commmand
        self._params["ephemeral"] = discord.app_commands.transformers.CommandParameter(
            name="ephemeral",
            description="Whether to send the command result ephemerally",
            required=False,
            default=None,
            type=discord.AppCommandOptionType.boolean,
        )

    async def _invoke_with_namespace(
        self,
        interaction: discord.Interaction,
        namespace: discord.app_commands.Namespace,
    ) -> T:
        if not await self._check_can_run(interaction):
            raise discord.app_commands.CheckFailure(
                f"The check functions for command {self.name!r} failed."
            )

        transformed_values = await self._transform_arguments(interaction, namespace)
        transformed_values.pop("ephemeral", None)
        return await self._do_call(interaction, transformed_values)


class AutoEphemeralHybridAppCommand(commands.hybrid.HybridAppCommand):
    def __init__(self, wrapped, app_command_name: Optional[str]) -> None:
        super().__init__(wrapped)
        self.name = app_command_name or self.name

        # Inject an `ephemeral` parameter to every hybrid commmand
        self._params["ephemeral"] = discord.app_commands.transformers.CommandParameter(
            name="ephemeral",
            description="Whether to send the command result ephemerally",
            required=False,
            default=None,
            type=discord.AppCommandOptionType.boolean,
        )


class AutoEphemeralHybridCommand(commands.HybridCommand):
    def __init__(self, func, /, **kwargs):
        app_command_name = kwargs.pop("app_command_name", None)
        super().__init__(func, **kwargs)
        self.app_command = (
            AutoEphemeralHybridAppCommand(self, app_command_name)
            if self.with_app_command
            else None
        )

    async def _parse_arguments(self, ctx: NeoContext):
        interaction = ctx.interaction

        if interaction is None:
            return await super()._parse_arguments(ctx)

        elif self.app_command:
            kwargs = await self.app_command._transform_arguments(
                interaction, interaction.namespace
            )
            kwargs.pop("ephemeral", None)
            ctx.kwargs = kwargs

    async def invoke(self, ctx: NeoContext, /) -> None:
        if self.with_command and ctx.interaction is None:
            return await super().invoke(ctx)

        if self.with_app_command and self.app_command and ctx.interaction is not None:
            return await super().invoke(ctx)

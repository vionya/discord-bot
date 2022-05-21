from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from neo.classes.context import NeoContext


class AutoEphemeralHybridAppCommand(commands.hybrid.HybridAppCommand):
    def __init__(self, wrapped):
        super().__init__(wrapped)

        # Inject an `ephemeral` parameter to every hybrid commmand
        self._params["ephemeral"] = discord.app_commands.transformers.CommandParameter(
            name="ephemeral",
            description="Whether to send the command result ephemerally",
            required=False,
            default=True,
            type=discord.AppCommandOptionType.boolean
        )


class AutoEphemeralHybridCommand(commands.HybridCommand):
    def __init__(self, func, /, **kwargs):
        super().__init__(func, **kwargs)
        self.app_command = AutoEphemeralHybridAppCommand(self) if self.with_app_command else None

    async def _parse_arguments(self, ctx):
        interaction = ctx.interaction

        if interaction is None:
            return await super()._parse_arguments(ctx)

        elif self.app_command:
            kwargs = await self.app_command._transform_arguments(interaction, interaction.namespace)
            ctx.ephemeral = kwargs.pop('ephemeral', True)
            ctx.kwargs = kwargs

    async def invoke(self, ctx: NeoContext, /) -> None:
        if self.with_command and ctx.interaction is None:
            return await super().invoke(ctx)

        if self.with_app_command and self.app_command and ctx.interaction is not None:
            return await super().invoke(ctx)

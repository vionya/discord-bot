import discord
from discord.ext import commands


class AutoEphemeralHybridAppCommand(commands.hybrid.HybridAppCommand):
    def __init__(self, wrapped):
        super().__init__(wrapped)

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
        self.app_command = AutoEphemeralHybridAppCommand(self)

    async def _parse_arguments(self, ctx):
        interaction = ctx.interaction
        if interaction is None:
            return await super()._parse_arguments(ctx)
        else:
            kwargs = await self.app_command._transform_arguments(interaction, interaction.namespace)
            ctx.ephemeral = kwargs.pop('ephemeral', True)
            ctx.kwargs = kwargs

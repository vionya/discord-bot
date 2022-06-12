# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

import re
import zoneinfo
from typing import TYPE_CHECKING, Any, Callable

import discord
from discord.app_commands import Transform, Transformer
from neo.types.commands import AnyCommand

if TYPE_CHECKING:
    from neo.classes.context import NeoContext

from discord.ext.commands import Converter

CODEBLOCK_REGEX = re.compile(r"^\w*\n", re.I)
EXTRACT_MENTION_REGEX = re.compile(r"<@!?(\d+)>")
EXTRACT_CHANNEL_REGEX = re.compile(r"^<#(\d{15,20})>$")


class WrapperTransformer(Transformer):
    wrapped: Callable[[str], Any]


def wrap_transformer(func: Callable[[str], Any]) -> WrapperTransformer:
    class Wrapper(WrapperTransformer):
        def __init__(self) -> None:
            super().__init__()
            self.wrapped = func

        @classmethod
        def transform(
            cls: Transform[Any, Transformer],
            interaction: discord.Interaction,
            value: str,
        ) -> Any:
            return func(value)

    return Wrapper()


@wrap_transformer
def bool_converter(maybe_bool: str) -> bool:
    normalized = maybe_bool.casefold()
    if normalized in ("yes", "y", "true", "t", "1", "enable", "on"):
        return True
    elif normalized in ("no", "n", "false", "f", "0", "disable", "off"):
        return False
    raise ValueError("Value must be interpretable as a boolean")


@wrap_transformer
def codeblock_converter(codeblock: str) -> str:
    new = None
    if all([codeblock.startswith("`"), codeblock.endswith("`")]):
        new = codeblock.strip("`")
        return re.sub(CODEBLOCK_REGEX, "", new)
    return codeblock


@wrap_transformer
def timezone_converter(timezone: str) -> str:
    try:
        zone = zoneinfo.ZoneInfo(timezone)
    except zoneinfo.ZoneInfoNotFoundError:
        raise ValueError("Provided timezone was invalid.")
    return str(zone)


@wrap_transformer
def mention_converter(mention: str) -> int:
    match = EXTRACT_MENTION_REGEX.match(mention)
    if not match:
        raise ValueError("Could not find a valid mention.")

    return int(match[1])


@wrap_transformer
def timeout_converter(provided_timeout: str) -> int:
    if not provided_timeout.isdigit():
        raise ValueError("`timeout` must be a number.")

    timeout = int(provided_timeout)
    if not (timeout >= 1 and timeout <= 5):
        raise ValueError("`timeout` must be between 1 and 5 (inclusive).")
    return timeout


@wrap_transformer
def max_days_converter(provided_max_days: str) -> int:
    if not provided_max_days.isdigit():
        raise ValueError("`max_days` must be a number.")

    max_days = int(provided_max_days)
    if not max_days > 1:
        raise ValueError("`max_days` may not be less than 1.")
    return max_days


class text_channel_transformer(Transformer):
    @classmethod
    def transform(
        cls, interaction: discord.Interaction, value: str
    ) -> discord.TextChannel:
        if not interaction.guild:
            raise AttributeError("This must be used in a guild.")

        match = EXTRACT_CHANNEL_REGEX.match(value)

        if match:
            channel_id = int(match.group(1))

            if isinstance(
                channel := interaction.guild.get_channel(channel_id),
                discord.TextChannel,
            ):
                return channel
            else:
                raise TypeError("A valid text channel must be provided")

        else:
            try:
                return next(
                    filter(
                        lambda ch: ch and ch.name == value,
                        interaction.guild.text_channels,
                    )
                )
            except StopIteration:
                raise TypeError("A valid text channel must be provided")


class command_converter(Converter[AnyCommand]):
    async def convert(self, ctx: NeoContext, command_name: str) -> AnyCommand:
        command = ctx.bot.get_command(command_name) or ctx.bot.tree.get_command(
            command_name, type=discord.AppCommandType.chat_input
        )
        if not command:
            raise NameError(f"There is no command by the identifier `{command_name}`.")
        return command

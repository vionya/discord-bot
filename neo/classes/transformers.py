# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

import re
import zoneinfo
from operator import attrgetter
from typing import TYPE_CHECKING, Generic, TypeVar

import discord
from discord.app_commands import Choice, Transformer
from neo.tools import recursive_get_command
from neo.types.commands import AnyCommand
from typing_extensions import Self

if TYPE_CHECKING:
    from collections.abc import Callable

    from neo import Neo

T = TypeVar("T")

CODEBLOCK_REGEX = re.compile(r"^\w*\n", re.I)
EXTRACT_MENTION_REGEX = re.compile(r"<@!?(\d+)>")
EXTRACT_CHANNEL_REGEX = re.compile(r"^<#(\d{15,20})>$")


class WrapperTransformer(Transformer, Generic[T]):
    wrapped: Callable[[str], T]

    @classmethod
    def transform(cls: type[Self], interaction: discord.Interaction, value: str) -> T:
        ...


def wrap_transformer(func: Callable[[str], T]) -> type[WrapperTransformer[T]]:
    class Wrapper(WrapperTransformer):
        def __init__(self) -> None:
            super().__init__()
            self.wrapped = func

        @classmethod
        def transform(cls, interaction, value):
            return func(value)

    return Wrapper


@wrap_transformer
def bool_transformer(maybe_bool: str) -> bool:
    normalized = maybe_bool.casefold()
    if normalized in ("yes", "y", "true", "t", "1", "enable", "on"):
        return True
    elif normalized in ("no", "n", "false", "f", "0", "disable", "off"):
        return False
    raise ValueError("Value must be interpretable as a boolean.")


@wrap_transformer
def codeblock_transformer(codeblock: str) -> str:
    new = None
    if codeblock.startswith("`") and codeblock.endswith("`"):
        new = codeblock.strip("`")
        return re.sub(CODEBLOCK_REGEX, "", new)
    return codeblock


@wrap_transformer
def timezone_transformer(timezone: str) -> str:
    try:
        zone = zoneinfo.ZoneInfo(timezone)
    except zoneinfo.ZoneInfoNotFoundError:
        raise ValueError("Provided timezone was invalid.")
    return str(zone)


@wrap_transformer
def mention_transformer(mention: str) -> int:
    match = EXTRACT_MENTION_REGEX.match(mention)
    if not match:
        raise ValueError("Could not find a valid mention.")

    return int(match[1])


@wrap_transformer
def timeout_transformer(provided_timeout: str) -> int:
    if not provided_timeout.isnumeric():
        raise ValueError("`timeout` must be a number.")

    timeout = int(provided_timeout)
    if not 1 <= timeout <= 5:
        raise ValueError("`timeout` must be between 1 and 5.")
    return timeout


@wrap_transformer
def max_days_transformer(provided_max_days: str) -> int:
    if not provided_max_days.isnumeric():
        raise ValueError("`max_days` must be a number.")

    max_days = int(provided_max_days)
    if max_days < 1:
        raise ValueError("`max_days` may not be less than 1.")
    return max_days


class text_channel_transformer(Transformer):
    @classmethod
    def transform(
        cls, interaction: discord.Interaction, value: str
    ) -> discord.TextChannel:
        if not interaction.guild:
            raise AttributeError("This must be used in a guild.")

        if match := EXTRACT_CHANNEL_REGEX.match(value):
            channel_id = int(match.group(1))

            if isinstance(
                channel := interaction.guild.get_channel(channel_id),
                discord.TextChannel,
            ):
                return channel
            else:
                raise TypeError("A valid text channel must be provided.")

        else:
            try:
                return next(
                    filter(
                        lambda ch: ch and ch.name == value,
                        interaction.guild.text_channels,
                    )
                )
            except StopIteration:
                raise TypeError("A valid text channel must be provided.")


class command_transformer(Transformer):
    @classmethod
    def transform(
        cls, interaction: discord.Interaction, command_name: str
    ) -> AnyCommand:
        bot: Neo = interaction.client  # type: ignore

        command = recursive_get_command(bot.tree, command_name)
        if not command:
            raise NameError(f"There is no command by the identifier `{command_name}`.")
        return command

    @classmethod
    async def autocomplete(
        cls, interaction: discord.Interaction, current: str
    ) -> list[Choice[str]]:
        bot: Neo = interaction.client  # type: ignore

        all_commands = map(attrgetter("qualified_name"), bot.tree.walk_commands())
        return [Choice(name=k, value=k) for k in all_commands if current in k][:25]

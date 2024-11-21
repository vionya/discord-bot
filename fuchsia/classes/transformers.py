# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 vionya
from __future__ import annotations

import re
import zoneinfo
from operator import attrgetter
from typing import TYPE_CHECKING, Generic, Iterable, TypeVar

import discord
from discord.app_commands import Choice, Transformer
from typing_extensions import Self

from fuchsia.tools import recursive_get_command
from fuchsia.types.commands import AnyCommand

if TYPE_CHECKING:
    from collections.abc import Callable

    from fuchsia import Fuchsia

T = TypeVar("T")

CODEBLOCK_REGEX = re.compile(r"^\w*\n", re.I)
EXTRACT_MENTION_REGEX = re.compile(r"<@!?(\d+)>")
EXTRACT_CHANNEL_REGEX = re.compile(r"^<#(\d{15,20})>$")


class WrapperTransformer(Transformer, Generic[T]):
    wrapped: Callable[[str], T]
    options: Iterable[str]

    @classmethod
    def transform(
        cls: type[Self], interaction: discord.Interaction, value: str
    ) -> T: ...


def wrap_transformer(_options: Iterable[str] = []):
    def inner(func: Callable[[str], T]) -> type[WrapperTransformer[T]]:
        class Wrapper(WrapperTransformer):
            options = _options

            def __init__(self) -> None:
                super().__init__()
                self.wrapped = func

            @classmethod
            def transform(cls, interaction, value):
                return func(value)

        return Wrapper

    return inner


@wrap_transformer(("True", "False"))
def bool_transformer(maybe_bool: str) -> bool:
    normalized = maybe_bool.casefold()
    if normalized in ("yes", "y", "true", "t", "1", "enable", "on"):
        return True
    elif normalized in ("no", "n", "false", "f", "0", "disable", "off"):
        return False
    raise ValueError("Value must be interpretable as a boolean.")


@wrap_transformer()
def codeblock_transformer(codeblock: str) -> str:
    new = None
    if codeblock.startswith("`") and codeblock.endswith("`"):
        new = codeblock.strip("`")
        return re.sub(CODEBLOCK_REGEX, "", new)
    return codeblock


@wrap_transformer(zoneinfo.available_timezones())
def timezone_transformer(timezone: str) -> str:
    try:
        zone = zoneinfo.ZoneInfo(timezone)
    except zoneinfo.ZoneInfoNotFoundError:
        raise ValueError("Provided timezone was invalid.")
    return str(zone)


@wrap_transformer()
def mention_transformer(mention: str) -> int:
    match = EXTRACT_MENTION_REGEX.match(mention)
    if not match:
        raise ValueError("Could not find a valid mention.")

    return int(match[1])


@wrap_transformer(("1", "2", "3", "4", "5"))
def timeout_transformer(provided_timeout: str) -> int:
    if not provided_timeout.isnumeric():
        raise ValueError("`timeout` must be a number.")

    timeout = int(provided_timeout)
    if not 1 <= timeout <= 5:
        raise ValueError("`timeout` must be between 1 and 5.")
    return timeout


@wrap_transformer()
def gt_zero_transformer(provided_val: str) -> int:
    if not provided_val.isnumeric():
        raise ValueError("Value must be a number.")

    val = int(provided_val)
    if val < 1:
        raise ValueError("Value may not be less than 1.")
    return val


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
        bot: Fuchsia = interaction.client  # type: ignore

        command = recursive_get_command(bot.tree, command_name)
        if not command:
            raise NameError(
                f"There is no command by the identifier `{command_name}`."
            )
        return command

    @classmethod
    async def autocomplete(
        cls, interaction: discord.Interaction, current: str
    ) -> list[Choice[str]]:
        bot: Fuchsia = interaction.client  # type: ignore

        all_commands = map(
            attrgetter("qualified_name"), bot.tree.walk_commands()
        )
        return [Choice(name=k, value=k) for k in all_commands if current in k][
            :25
        ]

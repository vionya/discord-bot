# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

import re
import zoneinfo
from types import MethodType
from typing import TYPE_CHECKING, Callable, ParamSpec, TypeVar

if TYPE_CHECKING:
    from neo.classes.context import NeoContext

from discord.ext.commands import Command, Converter

CODEBLOCK_REGEX = re.compile(r"^\w*\n", re.I)
EXTRACT_MENTION_REGEX = re.compile(r"<@!?(\d+)>")

T = TypeVar("T")


def wrap_converter(func: Callable[[str], T]) -> type[Converter[T]]:
    class WrapperConverter(Converter):
        async def convert(self: Converter[T], ctx: NeoContext, arg: str) -> T:
            return func(arg)

    return WrapperConverter


@wrap_converter
def codeblock_converter(codeblock: str) -> str:
    new = None
    if all([codeblock.startswith("`"), codeblock.endswith("`")]):
        new = codeblock.strip("`")
        return re.sub(CODEBLOCK_REGEX, "", new)
    return codeblock


@wrap_converter
def timezone_converter(timezone: str) -> str:
    try:
        zone = zoneinfo.ZoneInfo(timezone)
    except zoneinfo.ZoneInfoNotFoundError:
        raise ValueError("Provided timezone was invalid.")
    return str(zone)


@wrap_converter
def mention_converter(mention: str) -> int:
    match = EXTRACT_MENTION_REGEX.match(mention)
    if not match:
        raise ValueError("Could not find a valid mention.")

    return int(match[1])


@wrap_converter
def timeout_converter(provided_timeout: str) -> int:
    if not provided_timeout.isdigit():
        raise ValueError("`timeout` must be a number.")

    timeout = int(provided_timeout)
    if not (timeout >= 1 and timeout <= 5):
        raise ValueError("`timeout` must be between 1 and 5 (inclusive).")
    return timeout


@wrap_converter
def max_days_converter(provided_max_days: str) -> int:
    if not provided_max_days.isdigit():
        raise ValueError("`max_days` must be a number.")

    max_days = int(provided_max_days)
    if not max_days > 1:
        raise ValueError("`max_days` may not be less than 1.")
    return max_days


class command_converter(Converter):
    async def convert(self, ctx, command_name: str) -> Command:
        command = ctx.bot.get_command(command_name)
        if not command:
            raise NameError(f"There is no command by the identifier `{command_name}`.")
        return command

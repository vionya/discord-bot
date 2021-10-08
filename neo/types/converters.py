# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2021 sardonicism-04
import re
import zoneinfo
from types import MethodType

from discord.ext.commands import Converter

CODEBLOCK_REGEX = re.compile(r"^\w*\n", re.I)
EXTRACT_MENTION_REGEX = re.compile(r"<@!?(\d+)>")


def wrap_converter(func):
    converter_type: Converter = type(func.__name__, (Converter,), {})

    async def convert(self, ctx, arg):
        return func(arg)
    converter_type.convert = MethodType(convert, converter_type)
    return converter_type


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
    return int(EXTRACT_MENTION_REGEX.match(mention)[1])


@wrap_converter
def timeout_converter(timeout: str) -> int:
    if not timeout.isdigit():
        raise ValueError("`timeout` must be a number.")
    timeout = int(timeout)
    if not (timeout >= 1 and timeout <= 5):
        raise ValueError("`timeout` must be between 1 and 5 (inclusive).")
    return timeout


@wrap_converter
def max_days_converter(max_days: str) -> int:
    if not max_days.isdigit():
        raise ValueError("`max_days` must be a number.")
    max_days = int(max_days)
    if not max_days > 1:
        raise ValueError("`max_days` may not be less than 1.")
    return max_days

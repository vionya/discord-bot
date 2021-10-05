# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2021 sardonicism-04
import re
import zoneinfo

from discord.ext.commands import Converter

CODEBLOCK_REGEX = re.compile(r"^\w*\n", re.I)
EXTRACT_MENTION_REGEX = re.compile(r"<@!?(\d+)>")


class codeblock_converter(Converter):
    async def convert(self, ctx, codeblock: str) -> str:
        new = None
        if all([codeblock.startswith("`"), codeblock.endswith("`")]):
            new = codeblock.strip("`")
            return re.sub(CODEBLOCK_REGEX, "", new)
        return codeblock


class timezone_converter(Converter):
    async def convert(self, ctx, timezone: str) -> str:
        try:
            zone = zoneinfo.ZoneInfo(timezone)
        except zoneinfo.ZoneInfoNotFoundError:
            raise ValueError("Provided timezone was invalid.")
        return str(zone)


class mention_converter(Converter):
    async def convert(self, ctx, mention: str) -> int:
        return int(EXTRACT_MENTION_REGEX.match(mention)[1])


class timeout_converter(Converter):
    async def convert(self, ctx, timeout: str) -> int:
        if not timeout.isdigit():
            raise ValueError
        timeout = int(timeout)
        if not (timeout >= 1 and timeout <= 5):
            raise ValueError
        return timeout


class max_days_converter(Converter):
    async def converter(self, ctx, max_days: str) -> int:
        if not max_days.isdigit():
            raise ValueError
        max_days = int(max_days)
        if not max_days > 1:
            raise ValueError
        return max_days

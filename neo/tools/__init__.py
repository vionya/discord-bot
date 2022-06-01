# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations
import re

from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar

from discord import app_commands, utils
from discord.ext import commands

from .checks import is_registered_guild, is_registered_profile
from .decorators import instantiate, deprecate
from .patcher import Patcher

if TYPE_CHECKING:
    from neo.classes.context import NeoContext
    from neo.types.settings_mapping import SettingsMapping


T = TypeVar("T")


def shorten(text: str, width: int) -> str:
    if len(text) > width:
        text = text[: width - 3] + "..."
    return text


def try_or_none(func: Callable[..., T], *args, **kwargs) -> T | None:
    try:
        return func(*args, **kwargs)
    except Exception:
        return None


async def convert_setting(
    ctx: NeoContext, mapping: SettingsMapping, setting: str, new_value: str
):
    # Use try/except here because, if the __getitem__ succeeds,
    # it's roughly 30% faster than using dict.get. Because of the
    # subsequent operations on success, optimizing speed on success
    # is preferable. __getitem__ is slower than dict.get on failure,
    # but since failure leads straight to a `raise`, the difference is
    # negligible.
    try:
        valid_setting = mapping[setting]
    except KeyError:
        raise commands.BadArgument(
            "That's not a valid setting! " "Try `settings` for a list of settings!"
        )

    value = None

    converter = valid_setting["converter"]
    if isinstance(converter, commands.Converter):
        if (converted := await converter.convert(ctx, new_value)) is not None:
            value = converted

    elif (converted := try_or_none(converter, new_value)) is not None:
        value = converted

    else:
        raise commands.BadArgument(
            "Bad value provided for setting `{}`".format(setting)
        )

    return value


def recursive_getattr(target: Any, attr: str, default: Any = None) -> Any:
    # Get the named attribute from the target object
    # with a default of None
    found = getattr(target, attr, None)
    # If nothing is found, return the default
    if not found:
        return default

    # If `found` has no attribute named `attr` then return it
    # Otherwise, recurse until we do find something
    return (
        found if not hasattr(found, attr) else recursive_getattr(found, attr, default)
    )


# Recursively search for a child node of a command tree or group
def recursive_get_command(
    container: app_commands.CommandTree | app_commands.Group, command: str
) -> Optional[app_commands.Command | app_commands.Group]:
    # Split the named command into its parts
    command_path = command.split(" ")
    # The first item will become the next target for search
    new_container = container.get_command(command_path[0])
    # Shift the path
    command_path = command_path[1:]

    # If there's no path left, then max depth has been reached
    if len(command_path) == 0:
        return new_container

    # If there's another layer of tree/group, recurse
    elif isinstance(new_container, app_commands.Group | app_commands.CommandTree):
        return recursive_get_command(new_container, " ".join(command_path))

    # If all else fails, return None
    return None


def parse_ids(argument: str) -> tuple[int, Optional[int]]:
    id_regex = re.compile(
        r"(?:(?P<channel_id>[0-9]{15,20})-)?(?P<message_id>[0-9]{15,20})$"
    )
    link_regex = re.compile(
        r"https?://(?:(ptb|canary|www)\.)?discord(?:app)?\.com/channels/"
        r"(?P<guild_id>[0-9]{15,20}|@me)"
        r"/(?P<channel_id>[0-9]{15,20})/(?P<message_id>[0-9]{15,20})/?$"
    )
    match = id_regex.match(argument) or link_regex.match(argument)
    if not match:
        raise commands.MessageNotFound(argument)
    data = match.groupdict()
    channel_id = utils._get_as_snowflake(data, "channel_id")
    message_id = int(data["message_id"])
    return message_id, channel_id

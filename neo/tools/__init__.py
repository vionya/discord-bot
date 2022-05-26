# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, TypeVar
from discord.ext import commands

from .checks import is_registered_guild, is_registered_profile
from .patcher import Patcher

if TYPE_CHECKING:
    from neo.classes.context import NeoContext
    from neo.types.settings_mapping import SettingsMapping

T = TypeVar("T")


def shorten(text: str, width: int) -> str:
    if len(text) > width:
        text = text[:width - 3] + "..."
    return text


def try_or_none(func: Callable[..., T], *args, **kwargs) -> T | None:
    try:
        return func(*args, **kwargs)
    except Exception:
        return None


async def convert_setting(
    ctx: NeoContext,
    mapping: SettingsMapping,
    setting: str,
    new_value: str
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
            "That's not a valid setting! "
            "Try `settings` for a list of settings!"
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
    return found if not hasattr(found, attr) else \
        recursive_getattr(found, attr, default)

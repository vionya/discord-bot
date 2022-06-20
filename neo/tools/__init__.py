# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Literal, Optional, TypeGuard, TypeVar, overload

from discord import app_commands, utils

from .checks import is_registered_guild, is_registered_profile
from .decorators import deprecate, instantiate, with_docstring
from .message_helpers import prompt_user, send_confirmation
from .patcher import Patcher

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from discord import Interaction
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
    interaction: Interaction, mapping: SettingsMapping, setting: str, new_value: str
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
        raise NameError(
            "That's not a valid setting! " "Try `settings` for a list of settings!"
        )

    value = None

    transformer = valid_setting["transformer"]
    if isinstance(transformer, type) and issubclass(
        transformer, app_commands.Transformer
    ):
        if (
            converted := await utils.maybe_coroutine(
                transformer().transform, interaction, new_value
            )
        ) is not None:
            value = converted

    elif (converted := try_or_none(transformer, new_value)) is not None:
        value = converted

    else:
        raise ValueError("Bad value provided for setting `{}`".format(setting))

    return value


@overload
def recursive_getattr(target: Any, attr: str, /) -> Any:
    ...


@overload
def recursive_getattr(target: Any, attr: str, default: T, /) -> Any | T:
    ...


def recursive_getattr(*args):
    if len(args) > 3:
        raise TypeError(
            f"recursive_getattr expected at most 3 arguments, got {len(args)}"
        )

    target, attr, default = args

    # If the attribute isn't found on the target, return the default
    if not hasattr(target, attr):
        return default

    # Get the named attribute from the target object
    found = getattr(target, attr)

    # If `found` has no attribute named `attr` then return it
    # Otherwise, recurse until we do find something
    return (
        # `found` is now passed as the default as well as the target because
        # if the attribute doesn't exist on `found`
        found
        if not hasattr(found, attr)
        else recursive_getattr(found, attr, found)
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
        raise ValueError(f"Message {argument} not found")

    data = match.groupdict()
    channel_id = utils._get_as_snowflake(data, "channel_id")
    message_id = int(data["message_id"])
    return message_id, channel_id


ClearAllOption = "Clear all"


def generate_autocomplete_list(
    container: Sequence[Any],
    current: str,
    *,
    insert_wildcard: bool = False,
    show_previews: bool = True,
    focus_current: bool = True,
) -> list[app_commands.Choice[str] | app_commands.Choice[int]]:
    """
    Generate a list of choices suitable for an autocomplete function

    Parameters
    ----------
    container: Sequence[Any]
        The items from which the autocomplete list will be generated
    current: str
        The current value that the user has input
    insert_wildcard: bool
        Whether the wildcard character (`~`) should be prepended to the output
        Default: False
    show_previews: bool
        Whether previews of the content should be included alongside indices
        Default: True
    focus_current: bool
        Whether the list should adapt to show indices surrounding the current value
        Default: True
    """

    if len(current) == 0 or focus_current is False:
        # If the field is empty or focus_current is False,
        # the range simply goes from (1..min(container length + 1, 26 [or 25 if wildcard is enabled]))
        valid_range = range(1, min(len(container) + 1, 26 - int(insert_wildcard)))

    elif current.isnumeric():
        # If the field has a value, then the autocomplete will start with
        # the current value, and then show a range of indices surrounding
        # the current value
        user_index = int(current)

        if user_index < 0 or user_index > len(container):
            return []

        valid_range = []
        len_left = len(container[: user_index - 1])

        for i in [
            user_index,
            # start from at most 12 before the user index
            *range(user_index - min(len_left, 12), user_index),
            # go from the user index + 1 to the end of the container's length
            *range(user_index + 1, user_index + (len(container) - len_left)),
        ]:
            valid_range.append(i)
            if len(valid_range) == 25 - int(insert_wildcard):
                # break at 25 (or 24 if wildcard enabled) since that's the max allowed
                # number of autocomplete values
                break

    else:
        return []

    opts: list[str | int] = (
        [ClearAllOption, *valid_range] if insert_wildcard else [*valid_range]
    )

    opt_names: list[str] = []

    for opt in opts:
        opt_name = str(opt)
        if isinstance(opt, int) and show_previews is True:
            content = shorten(container[opt - 1], 50 - (len(opt_name) + 3))
            opt_name = f"{opt_name} - {content}"
        opt_names.append(opt_name)

    return [
        app_commands.Choice[Any](
            name=name, value=str(val) if insert_wildcard else int(val)
        )
        for name, val in zip(opt_names, opts)
    ]


def is_valid_index(value: str) -> TypeGuard[int]:
    return value.isnumeric()


def is_clear_all(value: str) -> TypeGuard[Literal["Clear all"]]:
    return value == ClearAllOption

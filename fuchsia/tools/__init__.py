# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 vionya
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Optional, ParamSpec, TypeVar, overload

from discord import app_commands, utils

# Module exports
from .autocomplete_helpers import (
    ClearAllOption,
    add_setting_autocomplete,
    generate_autocomplete_list,
    is_clear_all,
    is_valid_index,
    iter_autocomplete,
)
from .checks import is_registered_guild, is_registered_profile
from .decorators import deprecate, singleton, with_docstring
from .formatters import humanize_snake_case, shorten
from .message_helpers import prompt_user, send_confirmation
from .patcher import Patcher

if TYPE_CHECKING:
    from collections.abc import Callable

    from discord import Interaction

    from fuchsia.classes.containers import SettingsMapping

ID_PATTERN = re.compile(
    r"(?:(?P<channel_id>[0-9]{15,20})-)?(?P<message_id>[0-9]{15,20})"
)
URL_PATTERN = re.compile(
    r"https?://(?:(?:canary|ptb|www)\.)?discord(?:app)?\.com/channels/(?:[0-9]"
    r"{15,20})/(?P<channel_id>[0-9]{15,20})/(?P<message_id>[0-9]{15,20})"
)

T = TypeVar("T")
U = TypeVar("U")
P = ParamSpec("P")


def try_or_none(
    func: Callable[P, T], *args: P.args, **kwargs: P.kwargs
) -> T | None:
    try:
        return func(*args, **kwargs)
    except Exception:
        return None


async def convert_setting(
    interaction: Interaction,
    mapping: SettingsMapping,
    setting: str,
    new_value: str,
):
    if setting not in mapping:
        raise NameError("That's not a valid setting!")
    valid_setting = mapping[setting]

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
def recursive_getattr(target: object, attr: str, /) -> Any:
    """
    Recursively get a named attribute from an object.

    This function will recursively get the attribute `attr` from the target
    `target` while `hasattr(target, attr)` is True.

    Example:
    ```py
    class Nested:
        foo: Nested | int
        ...

    a = Nested(Nested(Nested(1)))  # a.foo.foo.foo = 1
    recursive_getattr(a, "foo") == 1  # True
    ```

    :param target: The object to get an attribute from
    :type target: ``object``

    :param attr: The name of the attribute to get
    :type attr: ``str``

    :returns: The recursively accessed attribute
    :rtype: ``Any``

    :raises AttributeError: If the named attribute does not exist
    """


@overload
def recursive_getattr(target: object, attr: str, default: T, /) -> Any | T:
    """
    Recursively get a named attribute from an object.

    This function will recursively get the attribute `attr` from the target
    `target` while `hasattr(target, attr)` is True.

    If the attribute is not found, then the value provided for `default` will
    be returned instead.

    Example:
    ```py
    class Nested:
        foo: Nested | int
        ...

    a = Nested(Nested(Nested(1)))  # a.foo.foo.foo = 1
    recursive_getattr(a, "foo", 2) == 1  # True
    recursive_getattr(a, "bar", 2) == 1  # False
    recursive_getattr(a, "bar", 2) == 2  # True
    ```

    :param target: The object to get an attribute from
    :type target: ``object``

    :param attr: The name of the attribute to get
    :type attr: ``str``

    :param default: The value to fallback to if the attribute does not exist
    :type default: ``T``

    :return: The recursively accessed attribute if it exists, otherwise the
    value provided to `default`
    :rtype: ``Any | T``
    """


def recursive_getattr(*args) -> Any:
    if len(args) > 3:
        raise TypeError(
            f"recursive_getattr expected at most 3 arguments, got {len(args)}"
        )

    if len(args) == 3:
        target, attr, default = args

        # If a default was provided and the attribute doesn't exist on the
        # target, return the default
        if not hasattr(target, attr):
            return default
    else:
        target, attr = args

        # If a default was not provided and the attribute doesn't exist on
        # the target, raise an AttributeError
        if not hasattr(target, attr):
            raise AttributeError(
                f"'{target.__name__}' object has no attribute '{attr}'"
            )

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
    """
    Recursively gets a command from a nested structure.

    Takes a fully qualified command name, and recursively gets each element in
    the name, starting at `container`, ending when it reaches the requested
    command, or when it fails.

    Example:

    - Assume a command tree with a command `/foo bar baz`
    - Calling `tree.get_command("foo bar baz")` returns `None`
    - `recursive_get_command(tree, "foo bar baz")` searches performs the
    following access chain:

        `tree.foo` -> `foo.bar` -> `bar.baz`, returning `bar.baz`

    :param container: The top level container to begin recursion from
    :type container: ``app_commands.CommandTree | app_commands.Group``

    :param command: The qualified command path to the target command
    :type command: ``str``

    :returns: The command if found, otherwise `None`
    :rtype: ``app_commands.Command | app_commands.Group | None``
    """
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
    elif isinstance(
        new_container, app_commands.Group | app_commands.CommandTree
    ):
        return recursive_get_command(new_container, " ".join(command_path))

    # If all else fails, return None
    return None


@overload
def parse_id(content: str) -> int:
    ...


@overload
def parse_id(
    content: str, *, with_channel: bool = True
) -> tuple[int, int | None]:
    ...


def parse_id(
    content: str, *, with_channel: bool = False
) -> tuple[int, int | None] | int:
    """
    Parse a message (and optionally channel) ID from an arbitrary representation

    Attempts to extract an ID from either a raw ID string, or from a message
    jump URL.

    If `with_channel` is `True`, this function returns a tuple of values, with
    the first being the message ID, and the second being the channel ID if it
    can be found.

    :param content: The text to attempt to parse an ID from
    :type content: ``str``

    :param with_channel: Whether to attempt extracting the channel ID
    :type with_channel: ``bool``

    :returns: The parsed ID(s)
    :rtype: ``tuple[int, int | None] | int``

    :raises ValueError: If the provided content has no valid parsings
    """
    match = ID_PATTERN.match(content) or URL_PATTERN.match(content)

    if not match:
        raise ValueError("No valid ID was provided")

    data = match.groupdict()
    message_id = int(data["message_id"])
    if not with_channel:
        return message_id

    if "channel_id" not in data:
        return (message_id, None)
    return (message_id, int(data["channel_id"]))

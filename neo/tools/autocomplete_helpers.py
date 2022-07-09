# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeGuard, overload

from discord import app_commands

from .formatters import shorten

if TYPE_CHECKING:
    from collections.abc import Sequence

    from discord.app_commands import Choice
    from neo.classes.containers import SettingsMapping

ClearAllOption = "Clear all"


@overload
def generate_autocomplete_list(
    container: Sequence[Any],
    current: str,
    *,
    insert_wildcard: Literal[True],
    show_previews: bool = True,
    focus_current: bool = True,
) -> list[Choice[str] | Choice[int]]:
    ...


@overload
def generate_autocomplete_list(
    container: Sequence[Any],
    current: str,
    *,
    insert_wildcard: bool = False,
    show_previews: bool = True,
    focus_current: bool = True,
) -> list[Choice[int]]:
    ...


def generate_autocomplete_list(
    container: Sequence[Any],
    current: str,
    *,
    insert_wildcard: bool = False,
    show_previews: bool = True,
    focus_current: bool = True,
):
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
    if not isinstance(current, str):
        return []

    if len(current) == 0 or focus_current is False:
        # If the field is empty or focus_current is False,
        # the range simply goes from (1..min(container length + 1, 26 [or 25 if wildcard is enabled]))
        valid_range = range(1, min(len(container) + 1, 26 - int(insert_wildcard)))

    elif current.isnumeric():
        # If the field has a value, then the autocomplete will start with
        # the current value, and then show a range of indices surrounding
        # the current value

        # Also, clamp it to 1 to prevent negative index oddities (though
        # they are still sometimes useful and can be used w/o autocomplete)
        user_index = max(int(current), 1)

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


def generate_setting_mapping_autocomplete(
    mapping: SettingsMapping, current: str
) -> list[Choice[str]]:
    """Generate a list of choices suitable for an autocomplete function of a settings mapping"""
    setting_pairs: list[tuple[str, str]] = []
    for k, v in mapping.items():
        setting_pairs.append((v.display_name, k))

    setting_pairs = [
        *filter(lambda pair: current.casefold() in pair[0].casefold(), setting_pairs)
    ][:25]

    return [
        app_commands.Choice(name=name, value=value) for name, value in setting_pairs
    ]

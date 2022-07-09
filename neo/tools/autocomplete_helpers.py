# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable, Literal, Optional, TypeGuard, overload

from discord import app_commands

from .formatters import shorten

if TYPE_CHECKING:
    from collections.abc import Sequence

    from discord import Interaction
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


def add_setting_autocomplete(
    mapping: SettingsMapping, *, setting_param: str, value_param: Optional[str] = None
):
    """
    Decorates a Command and automatically implements a settings-based autocomplete
    on it.

    Provided parameter names and a settings mapping, autocomplete callbacks
    are generated to provide options that are valid for each setting.

    Parameters
    ----------
    mapping: SettingsMapping
        The settings mapping from which autocompletes will be generated
    setting_param: str
        The name of the parameter which specifies the setting key
    value_param: Optional[str]
        The name of the parameter which specifies the new setting value
    """

    def inner(command: app_commands.Command):
        async def setting_param_autocomplete(
            interaction: Interaction, current: str
        ) -> list[Choice[str]]:
            setting_pairs: list[tuple[str, str]] = []
            for k, v in mapping.items():
                setting_pairs.append((v.display_name, k))

            # Filter to the first 25 entries which match the current input
            setting_pairs = [
                *filter(
                    lambda pair: current.casefold() in pair[0].casefold(), setting_pairs
                )
            ][:25]
            return [
                app_commands.Choice(name=name, value=value)
                for name, value in setting_pairs
            ]

        command.autocomplete(setting_param)(setting_param_autocomplete)

        if value_param is not None:

            async def value_param_autocomplete(
                interaction: Interaction, current: str
            ) -> list[Choice]:
                # If the setting param hasn't been filled in yet, return
                # an empty list
                if setting_param not in interaction.namespace:
                    return []

                # If the value in the namespace isn't a string due to
                # Discord resolution weirdness, return an empty list
                setting_param_value: str = interaction.namespace[setting_param]
                if not isinstance(setting_param_value, str):
                    return []

                setting = mapping[setting_param_value]
                values: Iterable[tuple[str, str] | str]

                # If an autocomplete function was provided for a single setting,
                # use its return value
                if "autocomplete_func" in setting:
                    values = setting["autocomplete_func"](interaction, current)
                # If an autocomplete values iterable was provided, use it
                elif "autocomplete_values" in setting:
                    values = setting["autocomplete_values"]
                # If the transformer has an `options` property, then it's
                # a WrapperTransformer, so we can try and use the options
                # as autocomplete values
                elif hasattr(setting["transformer"], "options"):
                    values = setting["transformer"].options
                # Otherwise, give up and return an empty list
                else:
                    return []

                options: list[tuple[str, str]] = []
                for item in values:
                    # If the item is a tuple, then it is representing the
                    # name and value as separate from each other
                    if isinstance(item, tuple):
                        options.append(item)
                    # If the item is a single string, then the name and value
                    # should be the same
                    elif isinstance(item, str):
                        options.append((item, item))
                    # Otherwise, a bad type was provided
                    else:
                        raise TypeError(
                            "Autocomplete must be a Sequence[tuple[str, str] | str]"
                        )

                # Return a list of choices, filtered to only values which contain the
                # current parameter input (and limited to 25 in length)
                return [
                    app_commands.Choice(name=name, value=value)
                    for name, value in filter(
                        lambda opt: current.casefold() in opt[0].casefold(), options
                    )
                ][:25]

            command.autocomplete(value_param)(value_param_autocomplete)

        return command

    return inner

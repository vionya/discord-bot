# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 vionya
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Optional, TypeGuard, overload

from discord import app_commands

from .formatters import shorten

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from discord import Interaction
    from discord.app_commands import Choice

    from fuchsia.classes.containers import SettingsMapping

ClearAllOption = "Clear all"


@overload
def generate_autocomplete_list(
    container: Sequence[Any],
    current: str,
    *,
    insert_wildcard: Literal[True],
    show_previews: bool = True,
    focus_current: bool = True,
    show_numbers: bool = False,
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
    show_numbers: bool = False,
) -> list[Choice[int]]:
    ...


def generate_autocomplete_list(
    container: Sequence[str],
    current: str,
    *,
    insert_wildcard: bool = False,
    show_previews: bool = True,
    focus_current: bool = True,
    show_numbers: bool = False,
):
    """
    Generate a list of choices suitable for an autocomplete function

    :param container: The items from which the autocomplete list will be
    generated
    :type container: ``Sequence[str]``

    :param current: The current value that the user has input
    :type current: ``str``

    :param insert_wildcard: Whether the wildcard character (`~`) should be
    prepended to the input
    :type insert_wildcard: ``bool``

    :param show_previews: Whether content previews should be included with indices
    :type show_previews: ``bool``

    :param focus_current: Whether the list should adapt to show indices around
    the current value
    :type focus_current: ``bool``

    :param show_numbers: Whether numeric indices should be included when show_previews
    is `True`
    :type show_numbers: ``bool``

    :returns: The list of autocomplete choices
    :rtype: ``list[Choice[Any]]``
    """
    if not isinstance(current, str):
        return []

    if len(current) == 0 or focus_current is False:
        # If the field is empty or focus_current is False,
        # the range simply goes from (1..min(container length + 1, 26 [or 25 if wildcard is enabled]))
        valid_range = range(
            1, min(len(container) + 1, 26 - int(insert_wildcard))
        )

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
        # Otherwise, try to find a match against the text content of the
        # items in the container
        valid_range = [
            idx
            for idx, val in enumerate(container, 1)
            if current.casefold() in val.casefold()
        ]

    opts: list[str | int] = (
        [ClearAllOption, *valid_range] if insert_wildcard else [*valid_range]
    )

    opt_names: list[str] = []

    for opt in opts:
        opt_name = str(opt)
        if isinstance(opt, int) and show_previews is True:
            prefix = f"{opt_name} - " * int(show_numbers)
            content = shorten(container[opt - 1], 100 - len(prefix))
            opt_name = f"{prefix}{content}"
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
    mapping: SettingsMapping,
    *,
    setting_param: str,
    value_param: Optional[str] = None,
):
    """
    Decorates a Command and automatically implements a settings-based autocomplete
    on it

    Provided parameter names and a settings mapping, autocomplete callbacks
    are generated to provide options that are valid for each setting.

    :param mapping: The settings mapping to use for autocomplete generation
    :type mapping: ``SettingsMapping``

    :param settings_param: The name of the command parameter that accepts the
    setting key
    :type settings_param: ``str``

    :param value_param: The name of the command parameter that accepts the new
    setting value
    :type value_param: ``Optional[str]``
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
                    lambda pair: current.casefold() in pair[0].casefold(),
                    setting_pairs,
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
                        lambda opt: current.casefold() in opt[0].casefold(),
                        options,
                    )
                ][:25]

            command.autocomplete(value_param)(value_param_autocomplete)

        return command

    return inner


def iter_autocomplete(options: Iterable[str], *, param: str):
    """
    Decorates a Command and adds an autocomplete to it given a list of options

    :param options: The iterable of options to use for autocomplete
    :type options: ``Iterable[str]``

    :param param: The name of the parameter to add the autocomplete to
    :type param: ``str``
    """

    def inner(command: app_commands.Command):
        async def _autocomplete_func(interaction: Interaction, current: str):
            matching = filter(
                lambda option: current.casefold() in option.casefold(), options
            )

            return [
                app_commands.Choice(name=opt, value=opt) for opt in matching
            ][:25]

        command.autocomplete(param)(_autocomplete_func)

        return command

    return inner

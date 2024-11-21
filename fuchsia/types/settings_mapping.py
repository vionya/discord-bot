# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 vionya
from typing import TYPE_CHECKING, Any, TypedDict

from typing_extensions import NotRequired, Required

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from discord import Interaction
    from discord.app_commands import Transformer


class SettingData(TypedDict, total=False):
    # A transformer to process user input with, producing a valid value
    transformer: Required[type[Transformer] | Callable[[str], Any]]
    # A user-facing description of this setting
    description: NotRequired[str | None]
    # A user-friendly alternate name for this setting to use in display
    name_override: NotRequired[str]
    # A function defining how this setting's values should be autocompleted
    autocomplete_func: NotRequired[
        Callable[[Interaction, str], Iterable[tuple[str, str] | str]]
    ]
    # A static collection of values to provide in autocompletion
    autocomplete_values: NotRequired[Iterable[tuple[str, str] | str]]

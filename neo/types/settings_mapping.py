# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from typing import TYPE_CHECKING, Any, TypedDict

from typing_extensions import NotRequired, Required

if TYPE_CHECKING:
    from collections.abc import Callable

    from discord.app_commands import Transformer


class SettingData(TypedDict, total=False):
    transformer: Required[type[Transformer] | Callable[[str], Any]]
    description: NotRequired[str | None]
    name_override: NotRequired[str]

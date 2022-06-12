# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from typing import TYPE_CHECKING, Any, Optional, TypedDict

if TYPE_CHECKING:
    from collections.abc import Callable

    from discord.app_commands import Transformer


class SettingData(TypedDict):
    transformer: Transformer | Callable[[str], Any]
    description: Optional[str]


SettingsMapping = dict[str, SettingData]

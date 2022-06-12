# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from typing import TYPE_CHECKING, Any, Callable, NewType, Optional, TypedDict

if TYPE_CHECKING:
    from discord.app_commands import Transformer


class SettingData(TypedDict):
    transformer: Transformer | Callable[[str], Any]
    description: Optional[str]


SettingsMapping = dict[str, SettingData]

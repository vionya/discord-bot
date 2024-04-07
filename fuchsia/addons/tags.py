# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 sardonicism-04
from __future__ import annotations

from collections import defaultdict
from enum import Enum

import discord
from discord import app_commands

import fuchsia
from fuchsia.tools.checks import is_registered_profile_predicate


class TagType(Enum):
    Content = 0
    Alias = 1


class Tag:
    __slots__ = ("pointer", "user_id", "name", "content", "pointer")

    def __init__(
        self, user_id: int, name: str, content: str | None, pointer: str | None
    ):
        self.user_id = user_id
        self.name = name
        self.content = content
        self.pointer = pointer

    @property
    def tag_type(self):
        return TagType.Content if self.content else TagType.Alias


class Tags(fuchsia.Addon, app_group=True, group_name="tag"):
    """Commands for managing tags"""

    def __init__(self, bot: fuchsia.Fuchsia):
        self.bot = bot
        self.tags: dict[str, dict[str, Tag]] = defaultdict(dict)

    async def addon_interaction_check(self, interaction: discord.Interaction) -> bool:
        return await is_registered_profile_predicate(interaction)

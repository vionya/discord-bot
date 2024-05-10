# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 sardonicism-04
from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Any

import discord

if TYPE_CHECKING:
    from collections.abc import Mapping

    from discord import Colour


class Embed(discord.Embed):
    color: Optional[int | Colour]
    title: Optional[str]
    url: Optional[str]
    description: Optional[str]

    def __init__(self, **kwargs):
        kwargs.setdefault("color", 0xF48EAD)
        super().__init__(**kwargs)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]):
        data = dict(data)
        data.setdefault("color", 0xF48EAD)
        return super().from_dict(data)


del discord  # Avoids re-exporting discord

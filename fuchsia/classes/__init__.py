# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord

if TYPE_CHECKING:
    import datetime

    from discord import Colour


class Embed(discord.Embed):
    colour: Optional[int | Colour]
    color: Optional[int | Colour]
    title: Optional[str]
    url: Optional[str]
    description: Optional[str]
    timestamp: Optional[datetime.datetime]

    def __init__(self, **kwargs):
        kwargs.setdefault("colour", 0xF48EAD)
        super().__init__(**kwargs)

    @classmethod
    def from_dict(cls, data: dict):
        data.setdefault("color", 0xF48EAD)
        return super().from_dict(data)


del discord  # Avoids re-exporting discord

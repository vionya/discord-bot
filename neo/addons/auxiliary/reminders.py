# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
"""
An auxiliary module for the `Reminders` addon
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from neo.tools.message_helpers import send_confirmation

if TYPE_CHECKING:
    from typing_extensions import Self

    from neo.addons.reminders import Reminder, Reminders


class ReminderEditModal(discord.ui.Modal):
    def __init__(
        self, addon: Reminders, *, title: str, reminder: Reminder, max_len: int
    ):
        self.addon = addon
        self.reminder = reminder
        self.content: discord.ui.TextInput[Self] = discord.ui.TextInput(
            label="Edit Reminder Content",
            style=discord.TextStyle.paragraph,
            default=self.reminder.content,
            min_length=1,
            max_length=max_len,
        )

        super().__init__(title=title, timeout=300)

        self.add_item(self.content)

    async def on_submit(self, interaction: discord.Interaction):
        # Guaranteed by the min length and required-ness of the field
        assert self.content.value

        self.reminder.content = self.content.value
        await self.addon.bot.db.execute(
            """
            UPDATE reminders
            SET
                content=$1
            WHERE
                reminder_id=$2 AND
                user_id=$3
            """,
            self.content.value,
            self.reminder.reminder_id,
            self.reminder.user_id,
        )

        await send_confirmation(interaction, ephemeral=True)

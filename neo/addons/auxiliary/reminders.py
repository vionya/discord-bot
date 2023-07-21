# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
"""
An auxiliary module for the `Reminders` addon
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from neo.tools.message_helpers import send_confirmation

if TYPE_CHECKING:
    from asyncpg import Pool
    from typing_extensions import Self

    from neo.addons.reminders import Reminder, Reminders


class ReminderEditModal(discord.ui.Modal):
    def __init__(self, db: Pool, *, reminder: Reminder):
        self.db = db
        self.reminder = reminder
        self.content: discord.ui.TextInput[Self] = discord.ui.TextInput(
            label="Edit Reminder Content",
            style=discord.TextStyle.paragraph,
            default=self.reminder.content,
            min_length=1,
            max_length=reminder.MAX_LEN,
        )

        super().__init__(title="Editing a Reminder", timeout=300)

        self.add_item(self.content)

    async def on_submit(self, interaction: discord.Interaction):
        # Guaranteed by the min length and required-ness of the field
        assert self.content.value

        self.reminder.content = self.content.value
        await self.db.execute(
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

        await send_confirmation(
            interaction, predicate="edited reminder", ephemeral=True
        )


class ReminderShowView(discord.ui.View):
    def __init__(self, db: Pool, *, reminder: Reminder):
        self.db = db
        self.reminder = reminder

        super().__init__()

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user.id == self.reminder.user_id

    @discord.ui.button(
        label="Edit Reminder", emoji="✏️", style=discord.ButtonStyle.primary
    )
    async def edit_reminder(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        modal = ReminderEditModal(self.db, reminder=self.reminder)
        await interaction.response.send_modal(modal)
        await modal.wait()

        # this generally shouldn't happen
        if not interaction.message:
            return

        # copy embed from message
        embed = interaction.message.embeds[0]
        # update its description with the new content
        embed.description = self.reminder.content
        # edit the original response
        await interaction.edit_original_response(embeds=[embed])

    @discord.ui.button(
        label="Delete Reminder", emoji="🗑️", style=discord.ButtonStyle.red
    )
    async def delete_reminder(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.reminder.delete()
        await send_confirmation(
            interaction, ephemeral=True, predicate="deleted reminder"
        )

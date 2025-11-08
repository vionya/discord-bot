# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 vionya
"""
An auxiliary module for the `Reminders` addon
"""
from __future__ import annotations

from typing import TYPE_CHECKING, cast

import discord

from fuchsia.tools.message_helpers import send_confirmation

if TYPE_CHECKING:
    from asyncpg import Pool
    from typing_extensions import Self

    from fuchsia.addons.reminders import Reminder


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


class ReminderShowRow(discord.ui.ActionRow):
    def __init__(self, db: Pool, *, reminder: Reminder):
        self.db = db
        self.reminder = reminder

        super().__init__(id=100)

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user.id == self.reminder.user_id

    @discord.ui.button(
        label="Edit", emoji="✏️", style=discord.ButtonStyle.primary
    )
    async def edit_reminder(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        modal = ReminderEditModal(self.db, reminder=self.reminder)
        await interaction.response.send_modal(modal)
        await modal.wait()

        # this generally shouldn't happen
        if not interaction.message:
            return

        assert isinstance(self.view, discord.ui.LayoutView)
        cast(discord.ui.TextDisplay, self.view.find_item(67)).content = self.reminder.content
        await interaction.edit_original_response(view=self.view)

    @discord.ui.button(
        label="Delete", emoji="🗑️", style=discord.ButtonStyle.red
    )
    async def delete_reminder(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.reminder.delete()

        # remove edit button
        self.remove_item(self.edit_reminder)
        # update this button to be disabled and say Reminder Deleted
        button.label = "Deleted"
        button.disabled = True

        await interaction.response.edit_message(view=self.view)

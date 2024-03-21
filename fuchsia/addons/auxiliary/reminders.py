# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
"""
An auxiliary module for the `Reminders` addon
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from fuchsia.tools.message_helpers import send_confirmation
from fuchsia.tools.time_parse import parse_relative

if TYPE_CHECKING:
    from asyncpg import Pool
    from typing_extensions import Self

    from fuchsia.addons.reminders import Reminder, Reminders


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

        # remove edit button
        self.remove_item(self.edit_reminder)
        # update this button to be disabled and say Reminder Deleted
        button.label = "Reminder Deleted"
        button.disabled = True

        await interaction.response.edit_message(view=self)


class RemindMeLaterModal(discord.ui.Modal):
    when: discord.ui.TextInput = discord.ui.TextInput(
        label="When should this reminder trigger again?",
        style=discord.TextStyle.short,
        default="30m",
        placeholder="30m",
        min_length=1,
        max_length=256,
    )

    def __init__(self, *, reminder: Reminder):
        self.reminder = reminder

        super().__init__(title="Remind Me Later", timeout=300)

    async def on_submit(self, interaction: discord.Interaction):
        assert self.when.value

        delta = parse_relative(self.when.value)[0]
        self.reminder.delta = delta
        await self.reminder.reschedule()

        await send_confirmation(
            interaction,
            predicate="rescheduled your reminder for <t:{0:.0f}>".format(
                (self.reminder.epoch + self.reminder.delta).timestamp()
            ),
        )


class ReminderDeliveryView(discord.ui.View):
    def __init__(self, *, reminder: Reminder):
        self.reminder = reminder

        super().__init__()

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user.id == self.reminder.user_id

    @discord.ui.button(
        label="Remind Me Later", emoji="⏰", style=discord.ButtonStyle.primary
    )
    async def remind_later(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        modal = RemindMeLaterModal(reminder=self.reminder)
        await interaction.response.send_modal(modal)
        await modal.wait()

        button.disabled = True
        await interaction.response.edit_message(view=self)

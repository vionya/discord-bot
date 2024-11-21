# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 vionya
"""
An auxiliary module for the `Todos` addon
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

import discord

from fuchsia.tools.message_helpers import send_confirmation

if TYPE_CHECKING:
    from typing_extensions import Self

    from fuchsia.addons.todos import Todos


class TodoItem:
    # Max number of characters in a todo's content
    MAX_LEN = 1500

    __slots__ = ("user_id", "content", "todo_id", "created_at")

    def __init__(
        self,
        *,
        user_id: int,
        content: str,
        todo_id: UUID,
        created_at: datetime,
    ):
        self.user_id = user_id
        self.content = content
        self.todo_id = todo_id
        self.created_at = created_at

    def __repr__(self):
        return (
            '<{0.__class__.__name__} user_id={0.user_id} todo_id="{0.todo_id}">'
        ).format(self)


class TodoAddModal(discord.ui.Modal, title="Creating a Todo"):
    content: discord.ui.TextInput[Self] = discord.ui.TextInput(
        label="Todo Content",
        style=discord.TextStyle.paragraph,
        min_length=1,
        max_length=TodoItem.MAX_LEN,
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Guaranteed by the min length and required-ness of the field
        assert self.content.value
        self.interaction = interaction


class TodoEditModal(discord.ui.Modal):
    def __init__(self, addon: Todos, *, todo: TodoItem):
        self.addon = addon
        self.todo = todo
        self.content: discord.ui.TextInput[Self] = discord.ui.TextInput(
            label="Edit Todo Content",
            style=discord.TextStyle.paragraph,
            default=self.todo.content,
            min_length=1,
            max_length=TodoItem.MAX_LEN,
        )

        super().__init__(title="Editing a Todo", timeout=300)
        self.add_item(self.content)

    async def on_submit(self, interaction: discord.Interaction):
        # Guaranteed by the min length and required-ness of the field
        assert self.content.value

        self.todo.content = self.content.value
        await self.addon.bot.db.execute(
            """
            UPDATE todos
            SET
                content=$1
            WHERE
                todo_id=$2 AND
                user_id=$3
            """,
            self.content.value,
            self.todo.todo_id,
            self.todo.user_id,
        )

        await send_confirmation(
            interaction, ephemeral=True, predicate="edited todo"
        )


class TodoShowView(discord.ui.View):
    def __init__(self, addon: Todos, *, todo: TodoItem):
        super().__init__()
        self.addon = addon
        self.todo = todo

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user.id == self.todo.user_id

    @discord.ui.button(
        label="Edit Todo", emoji="✏️", style=discord.ButtonStyle.primary
    )
    async def edit_todo(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        modal = TodoEditModal(self.addon, todo=self.todo)
        await interaction.response.send_modal(modal)
        await modal.wait()

        # this generally shouldn't happen
        if not interaction.message:
            return

        # copy embed from message
        embed = interaction.message.embeds[0]
        # update its description with the new content
        embed.description = self.todo.content
        # edit the original response
        await interaction.edit_original_response(embeds=[embed])

    @discord.ui.button(
        label="Delete Todo", emoji="🗑️", style=discord.ButtonStyle.red
    )
    async def delete_todo(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.addon.bot.db.execute(
            """
            DELETE FROM todos WHERE
                todo_id=$1 AND
                user_id=$2
            """,
            self.todo.todo_id,
            interaction.user.id,
        )
        self.addon.todos[self.todo.user_id].remove(self.todo)

        # remove edit button
        self.remove_item(self.edit_todo)
        # update this button to be disabled and say Todo Deleted
        button.label = "Todo Deleted"
        button.disabled = True

        await interaction.response.edit_message(view=self)

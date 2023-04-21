# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
"""
An auxiliary module for the `Todos` addon
"""
from __future__ import annotations
from operator import attrgetter

from typing import TYPE_CHECKING

import discord

from neo.tools.message_helpers import send_confirmation

if TYPE_CHECKING:
    from typing_extensions import Self

    from neo.addons.todos import TodoItem, Todos


class TodoEditModal(discord.ui.Modal):
    def __init__(self, addon: Todos, *, todo: TodoItem):
        self.addon = addon
        self.todo = todo
        self.content: discord.ui.TextInput[Self] = discord.ui.TextInput(
            label="Edit Todo Content",
            style=discord.TextStyle.paragraph,
            default=self.todo.content,
            min_length=1,
            max_length=1500,
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

        await send_confirmation(interaction, ephemeral=True)


class TodoShowView(discord.ui.View):
    def __init__(self, addon: Todos, *, todo: TodoItem):
        super().__init__()
        self.addon = addon
        self.todo = todo

    @discord.ui.button(
        label="Edit Todo", emoji="✏️", style=discord.ButtonStyle.primary
    )
    async def edit_todo(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        modal = TodoEditModal(self.addon, todo=self.todo)
        await interaction.response.send_modal(modal)

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
        await send_confirmation(interaction, ephemeral=True)

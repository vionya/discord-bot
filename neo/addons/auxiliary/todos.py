# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
"""
An auxiliary module for the `Todos` addon
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from neo.tools.message_helpers import send_confirmation

if TYPE_CHECKING:
    from neo.addons.todos import TodoItem, Todos
    from typing_extensions import Self


class TodoEditModal(discord.ui.Modal):
    def __init__(self, addon: Todos, *, title: str, todo: TodoItem):
        self.addon = addon
        self.todo = todo
        self.content: discord.ui.TextInput[Self] = discord.ui.TextInput(
            label="Edit Todo Content",
            style=discord.TextStyle.paragraph,
            default=self.todo.content,
            min_length=1,
            max_length=1500,
        )

        super().__init__(title=title)

        self.add_item(self.content)

    async def on_submit(self, interaction: discord.Interaction):
        # Guaranteed by the min length and required-ness of the field
        assert self.content.value

        self.todo.content = self.content.value
        self.todo.edited = True
        await self.addon.bot.db.execute(
            """
            UPDATE todos
            SET
                content=$1,
                edited=TRUE
            WHERE
                todo_id=$2 AND
                user_id=$3
            """,
            self.content.value,
            self.todo.todo_id,
            self.todo.user_id,
        )

        await send_confirmation(interaction, ephemeral=True)

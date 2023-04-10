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
    def __init__(
        self, addon: Todos, *, title: str, todo: TodoItem, categories: list[str]
    ):
        self.addon = addon
        self.todo = todo
        self.content: discord.ui.TextInput[Self] = discord.ui.TextInput(
            label="Edit Todo Content",
            style=discord.TextStyle.paragraph,
            default=self.todo.content,
            min_length=1,
            max_length=1500,
        )

        # TODO: Uncomment when officially supported
        # self.category: discord.ui.Select[Self] = discord.ui.Select(
        #     placeholder="Change Todo Category",
        #     options=[
        #         discord.SelectOption(
        #             label=category.title(),
        #             value=category.casefold(),
        #             default=category == (todo.category or "Uncategorized").casefold(),
        #         )
        #         for category in map(str.casefold, [*categories, "Uncategorized"])
        #     ],
        # )

        super().__init__(title=title, timeout=300)

        self.add_item(self.content)
        # self.add_item(self.category)  TODO: Uncomment when supported

    async def on_submit(self, interaction: discord.Interaction):
        # Guaranteed by the min length and required-ness of the field
        assert self.content.value

        self.todo.content = self.content.value

        # TODO: Uncomment when supported
        # if len(self.category.values) == 1:
        #     new_category = self.category.values[0]
        #     if new_category == "uncategorized":
        #         new_category = None

        #     self.todo.category = new_category

        #     await self.addon.bot.db.execute(
        #         """
        #         UPDATE todos
        #         SET
        #             content=$1,
        #             category=$2
        #         WHERE
        #             todo_id=$3 AND
        #             user_id=$4
        #         """,
        #         self.content.value,
        #         new_category,
        #         self.todo.todo_id,
        #         self.todo.user_id,
        #     )
        # else:
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
    def __init__(self, addon: Todos, *, todo: TodoItem, categories: list[str]):
        super().__init__()
        self.addon = addon
        self.todo = todo
        self.categories = categories

    @discord.ui.button(
        label="Edit Todo", emoji="✏️", style=discord.ButtonStyle.primary
    )
    async def edit_todo(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        modal = TodoEditModal(
            self.addon,
            title="Editing a Todo",
            todo=self.todo,
            categories=self.categories,
        )
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

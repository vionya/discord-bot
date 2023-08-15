# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from operator import attrgetter
from typing import Optional
from uuid import UUID, uuid4

import discord
from discord import app_commands
from discord.utils import escape_markdown

import neo
from neo.addons.auxiliary.todos import TodoEditModal, TodoShowView
from neo.classes.app_commands import no_defer
from neo.modules import ButtonsMenu
from neo.tools import (
    generate_autocomplete_list,
    is_clear_all,
    is_valid_index,
    send_confirmation,
    shorten,
)
from neo.tools.checks import is_registered_profile_predicate

MAX_TODOS = 1000


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


class Todos(neo.Addon, app_group=True, group_name="todo"):
    """Commands for managing a todo list"""

    def __init__(self, bot: neo.Neo):
        self.bot = bot
        self.todos: defaultdict[int, list[TodoItem]] = defaultdict(list)
        asyncio.create_task(self.__ainit__())

    async def __ainit__(self):
        await self.bot.wait_until_ready()

        for record in await self.bot.db.fetch("SELECT * FROM todos"):
            self.todos[record["user_id"]].append(TodoItem(**record))

    # Need to dynamically account for deleted profiles
    @neo.Addon.recv("profile_delete")
    async def handle_deleted_profile(self, user_id: int):
        self.todos.pop(user_id, None)

    async def addon_interaction_check(
        self, interaction: discord.Interaction
    ) -> bool:
        return is_registered_profile_predicate(interaction)

    @app_commands.command(name="list")
    async def todo_list(self, interaction: discord.Interaction):
        """List your todos"""
        formatted_todos: list[str] = []
        todos: list[TodoItem] = self.todos[interaction.user.id]

        # sort in-place, by created_at ascending
        for todo in sorted(todos, key=lambda t: t.created_at):
            content = escape_markdown(
                shorten("".join(todo.content.splitlines()), width=75)
            )
            formatted_todos.append(f"- {content}")

        menu = ButtonsMenu.from_iterable(
            formatted_todos or ["No todos"],
            per_page=10,
            use_embed=True,
            template_embed=neo.Embed()
            .set_author(
                name=f"{interaction.user}'s todos",
                icon_url=interaction.user.display_avatar,
            )
            .set_footer(text=f"{len(todos)}/{MAX_TODOS} slots used"),
        )
        await menu.start(interaction)

    @app_commands.command(name="add")
    @app_commands.describe(content="The content of the new todo")
    async def todo_add(
        self,
        interaction: discord.Interaction,
        content: app_commands.Range[str, 1, TodoItem.MAX_LEN],
    ):
        """Add a new todo"""
        if len(self.todos[interaction.user.id]) >= MAX_TODOS:
            raise ValueError("You've used up all your todo slots!")

        data = {
            "user_id": interaction.user.id,
            "content": content,
            "todo_id": uuid4(),
            "created_at": datetime.now(timezone.utc),
        }

        await self.bot.db.execute(
            """
            INSERT INTO todos (
                user_id,
                content,
                todo_id,
                created_at
            ) VALUES (
                $1, $2, $3, $4
            )
            """,
            *data.values(),
        )

        self.todos[interaction.user.id].append(TodoItem(**data))
        await send_confirmation(
            interaction,
            predicate="added `{}` to your todo list".format(
                escape_markdown(content.replace("`", "`\u200b"))
            ),
        )

    @app_commands.command(name="remove")
    @app_commands.rename(index="todo")
    @app_commands.describe(index="A todo to remove")
    async def todo_remove(
        self,
        interaction: discord.Interaction,
        index: str,
    ):
        """Remove a todo"""
        if is_clear_all(index):
            todos = self.todos[interaction.user.id].copy()
            self.todos[interaction.user.id].clear()

        elif is_valid_index(index):
            try:
                todos = [self.todos[interaction.user.id].pop(int(index) - 1)]
            except IndexError:
                raise IndexError(
                    "One or more of the provided indices is invalid."
                )

        else:
            raise TypeError("Invalid input provided.")

        await self.bot.db.execute(
            """
            DELETE FROM todos WHERE
                todo_id=ANY($1::UUID[]) AND
                user_id=$2
            """,
            [*map(attrgetter("todo_id"), todos)],
            interaction.user.id,
        )
        await send_confirmation(interaction, predicate="updated your todo list")

    @todo_remove.autocomplete("index")
    async def todo_remove_autocomplete(
        self, interaction: discord.Interaction, current
    ):
        if interaction.user.id not in self.bot.profiles:
            return []

        todos = [todo.content for todo in self.todos[interaction.user.id]]
        return generate_autocomplete_list(todos, current, insert_wildcard=True)

    @app_commands.command(name="view")
    @app_commands.rename(index="todo")
    @app_commands.describe(index="A todo to view")
    async def todo_view(self, interaction: discord.Interaction, index: int):
        """View a todo"""
        try:
            todo = self.todos[interaction.user.id][index - 1]
        except IndexError:
            raise IndexError("Couldn't find that todo.")

        embed = (
            neo.Embed(description=todo.content)
            .add_field(
                name="Created at:",
                value=f"<t:{int(todo.created_at.timestamp())}>",
                inline=False,
            )
            .set_author(
                name="Viewing a todo",
                icon_url=interaction.user.display_avatar,
            )
        )

        await interaction.response.send_message(
            embed=embed,
            view=TodoShowView(self, todo=todo),
        )

    @app_commands.command(name="edit")
    @app_commands.rename(index="todo")
    @app_commands.describe(index="A todo to edit")
    @no_defer
    async def todo_edit(self, interaction: discord.Interaction, index: int):
        """Edit the content of a todo"""
        try:
            todo: TodoItem = self.todos[interaction.user.id][index - 1]
        except IndexError:
            raise IndexError("Couldn't find that todo.")

        modal = TodoEditModal(self, todo=todo)
        await interaction.response.send_modal(modal)

    @todo_view.autocomplete("index")
    @todo_edit.autocomplete("index")
    async def todo_edit_view_autocomplete(
        self, interaction: discord.Interaction, current
    ):
        if interaction.user.id not in self.bot.profiles:
            return []

        todos = [todo.content for todo in self.todos[interaction.user.id]]
        return generate_autocomplete_list(todos, current)


async def setup(bot):
    await bot.add_cog(Todos(bot))

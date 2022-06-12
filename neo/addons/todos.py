# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from operator import attrgetter
from uuid import UUID, uuid4

import discord
import neo
from discord import app_commands
from discord.utils import escape_markdown
from neo.addons.auxiliary.todos import TodoEditModal
from neo.modules import ButtonsMenu
from neo.tools import is_registered_profile, send_confirmation, shorten
from neo.tools.decorators import no_defer

MAX_TODOS = 100


class TodoItem:
    __slots__ = ("user_id", "content", "todo_id", "created_at", "edited")

    def __init__(
        self,
        *,
        user_id: int,
        content: str,
        todo_id: UUID,
        created_at: datetime,
        edited: bool,
    ):
        self.user_id = user_id
        self.content = content
        self.todo_id = todo_id
        self.created_at = created_at
        self.edited = edited

    def __repr__(self):
        return (
            "<{0.__class__.__name__} user_id={0.user_id} todo_id={0.todo_id}>".format(
                self
            )
        )


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

    @app_commands.command(name="list")
    @is_registered_profile()
    async def todo_list(self, interaction: discord.Interaction):
        """List your todos"""
        formatted_todos = []

        for index, todo in enumerate(self.todos[interaction.user.id], 1):
            formatted_todos.append(
                "`{0}` {1}".format(
                    index, escape_markdown(shorten(todo.content, width=75))
                )
            )

        menu = ButtonsMenu.from_iterable(
            formatted_todos or ["No todos"],
            per_page=10,
            use_embed=True,
            template_embed=neo.Embed().set_author(
                name=f"{interaction.user}'s todos",
                icon_url=interaction.user.display_avatar,
            ),
        )
        await menu.start(interaction)

    @app_commands.command(name="add")
    @app_commands.describe(content="The content of the new todo")
    @is_registered_profile()
    async def todo_add(self, interaction: discord.Interaction, content: str):
        """Add a new todo"""
        if len(self.todos[interaction.user.id]) >= MAX_TODOS:
            raise ValueError("You've used up all your todo slots!")

        if len(content) > 1500:
            raise ValueError("Todo content may be no more than 1500 characters long")

        data = {
            "user_id": interaction.user.id,
            "content": content,
            "todo_id": uuid4(),
            "created_at": datetime.now(timezone.utc),
            "edited": False,
        }

        await self.bot.db.execute(
            """
            INSERT INTO todos (
                user_id,
                content,
                todo_id,
                created_at,
                edited
            ) VALUES (
                $1, $2, $3, $4, $5
            )
            """,
            *data.values(),
        )

        self.todos[interaction.user.id].append(TodoItem(**data))
        await send_confirmation(interaction)

    @app_commands.command(name="remove")
    @app_commands.describe(index='A todo index to remove, or "~" to clear all')
    @is_registered_profile()
    async def todo_remove(self, interaction: discord.Interaction, index: str):
        """
        Remove a todo by index

        Passing `~` will remove all todos at once
        """
        if index.isnumeric():
            indices = [int(index)]
        elif index == "~":
            indices = ["~"]
        else:
            raise ValueError("Invalid input for index.")

        if "~" in indices:
            todos = self.todos[interaction.user.id].copy()
            self.todos[interaction.user.id].clear()

        else:
            (indices := [*map(str, indices)]).sort(
                reverse=True
            )  # Pop in an way that preserves the list's original order
            try:
                todos = [
                    self.todos[interaction.user.id].pop(index - 1)
                    for index in map(int, filter(str.isdigit, indices))
                ]
            except IndexError:
                raise IndexError("One or more of the provided indices is invalid.")

        await self.bot.db.execute(
            """
            DELETE FROM todos WHERE
                todo_id=ANY($1::TEXT[]) AND
                user_id=$2
            """,
            [*map(attrgetter("todo_id"), todos)],
            interaction.user.id,
        )
        await send_confirmation(interaction)

    @todo_remove.autocomplete("index")
    async def todo_remove_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        if interaction.user.id not in self.bot.profiles:
            return []

        opts: list[str | int] = ["~"]
        opts.extend([*range(1, len(self.todos[interaction.user.id]) + 1)][:24])
        return [
            *map(
                lambda opt: discord.app_commands.Choice(name=opt, value=opt),
                map(str, opts),
            )
        ]

    @app_commands.command(name="view")
    @app_commands.describe(index="A todo index to view")
    @is_registered_profile()
    async def todo_view(self, interaction: discord.Interaction, index: int):
        """View a todo by its listed index"""
        try:
            todo = self.todos[interaction.user.id][index - 1]
        except IndexError:
            raise IndexError("Couldn't find that todo.")

        embed = (
            neo.Embed(description=todo.content)
            .add_field(
                name=f"Created on <t:{int(todo.created_at.timestamp())}>",
                value="This todo has{}been edited".format(
                    " not " if not todo.edited else " "
                ),
            )
            .set_author(
                name="Viewing a todo",
                icon_url=interaction.user.display_avatar,
            )
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="edit")
    @app_commands.describe(index="A todo index to edit")
    @is_registered_profile()
    @no_defer
    async def todo_edit(self, interaction: discord.Interaction, index: int):
        """Edit the content of a todo"""
        try:
            todo: TodoItem = self.todos[interaction.user.id][index - 1]
        except IndexError:
            raise IndexError("Couldn't find that todo.")

        modal = TodoEditModal(self, title="Editing a Todo", todo=todo)
        await interaction.response.send_modal(modal)

    @todo_view.autocomplete("index")
    @todo_edit.autocomplete("index")
    async def todo_edit_view_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        if interaction.user.id not in self.bot.profiles:
            return []

        opts = [*range(1, len(self.todos[interaction.user.id]) + 1)][:24]
        return [
            *map(
                lambda opt: discord.app_commands.Choice(name=opt, value=int(opt)),
                map(str, opts),
            )
        ]


async def setup(bot):
    await bot.add_cog(Todos(bot))

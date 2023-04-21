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
    instantiate,
    is_clear_all,
    is_valid_index,
    send_confirmation,
    shorten,
    with_docstring,
)
from neo.tools.checks import is_registered_profile_predicate

MAX_TODOS = 100
MAX_TODO_CATEGORIES = 10
MAX_CATEGORY_LEN = 100


class TodoItem:
    __slots__ = ("user_id", "content", "todo_id", "created_at", "category")

    def __init__(
        self,
        *,
        user_id: int,
        content: str,
        todo_id: UUID,
        created_at: datetime,
        category: str | None,
    ):
        self.user_id = user_id
        self.content = content
        self.todo_id = todo_id
        self.created_at = created_at
        self.category = category

    def __repr__(self):
        return (
            '<{0.__class__.__name__} user_id={0.user_id} todo_id="{0.todo_id}"'
            ' category="{0.category}">'
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

    def _category_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        if interaction.user.id not in self.bot.profiles:
            return []

        profile = self.bot.profiles[interaction.user.id]
        return [
            app_commands.Choice(name=cat.title(), value=cat)
            for cat in profile.todo_categories
            if current.casefold() in cat
        ][:25]

    @app_commands.command(name="list")
    @app_commands.describe(category="The category to display todos from")
    async def todo_list(
        self, interaction: discord.Interaction, category: Optional[str] = None
    ):
        """List your todos"""
        formatted_todos: dict[str | None, list[str]] = defaultdict(list)

        todos: list[TodoItem] = []
        if category is None:
            todos = self.todos[interaction.user.id]
        else:
            todos = [
                todo
                for todo in self.todos[interaction.user.id]
                if todo.category == category
            ]

        for todo in todos:
            formatted_todos[todo.category].append(
                "- {0}".format(escape_markdown(shorten(todo.content, width=75)))
            )

        output: list[str] = []
        for cat, cat_fmted_todos in sorted(
            formatted_todos.items(), key=lambda x: x[0] is None, reverse=True
        ):
            if len(cat_fmted_todos) == 0:
                continue

            cat_name = f"**{(cat or 'Uncategorized').title()}**:"
            output.append(
                "{0}\n{1}".format(cat_name, "\n".join(cat_fmted_todos))
            )

        menu = ButtonsMenu.from_iterable(
            "\n\n".join(output).splitlines(keepends=True) or ["No todos"],
            per_page=10,
            use_embed=True,
            joiner="",
            template_embed=neo.Embed().set_author(
                name=f"{interaction.user}'s todos",
                icon_url=interaction.user.display_avatar,
            ),
        )
        await menu.start(interaction)

    @app_commands.command(name="add")
    @app_commands.describe(
        content="The content of the new todo",
        category="The category this todo will belong to",
    )
    async def todo_add(
        self,
        interaction: discord.Interaction,
        content: str,
        category: Optional[str] = None,
    ):
        """Add a new todo"""
        if len(self.todos[interaction.user.id]) >= MAX_TODOS:
            raise ValueError("You've used up all your todo slots!")

        if len(content) > 1500:
            raise ValueError(
                "Todo content may be no more than 1500 characters long"
            )

        data = {
            "user_id": interaction.user.id,
            "content": content,
            "todo_id": uuid4(),
            "created_at": datetime.now(timezone.utc),
            "category": category,
        }

        await self.bot.db.execute(
            """
            INSERT INTO todos (
                user_id,
                content,
                todo_id,
                created_at,
                category
            ) VALUES (
                $1, $2, $3, $4, $5
            )
            """,
            *data.values(),
        )

        self.todos[interaction.user.id].append(TodoItem(**data))
        await send_confirmation(interaction)

    @todo_list.autocomplete("category")
    @todo_add.autocomplete("category")
    async def todo_list_add_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        return self._category_autocomplete(interaction, current)

    @app_commands.command(name="remove")
    @app_commands.rename(index="todo")
    @app_commands.describe(index="A todo index to remove")
    async def todo_remove(
        self,
        interaction: discord.Interaction,
        index: str,
    ):
        """Remove a todo by index"""
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
        await send_confirmation(interaction)

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
    @app_commands.describe(index="A todo index to view")
    async def todo_view(self, interaction: discord.Interaction, index: int):
        """View a todo by its listed index"""
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

        if todo.category is not None:
            embed.add_field(
                name="Category:", value=todo.category.title(), inline=False
            )

        categories = [
            cat.title()
            for cat in self.bot.profiles[interaction.user.id].todo_categories
        ]

        await interaction.response.send_message(
            embed=embed,
            view=TodoShowView(self, todo=todo, categories=categories),
        )

    @app_commands.command(name="edit")
    @app_commands.rename(index="todo")
    @app_commands.describe(index="A todo index to edit")
    @no_defer
    async def todo_edit(self, interaction: discord.Interaction, index: int):
        """Edit the content of a todo"""
        try:
            todo: TodoItem = self.todos[interaction.user.id][index - 1]
        except IndexError:
            raise IndexError("Couldn't find that todo.")

        categories = [
            cat.title()
            for cat in self.bot.profiles[interaction.user.id].todo_categories
        ]
        modal = TodoEditModal(self, todo=todo, categories=categories)
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

    @instantiate
    class Category(app_commands.Group):
        """Commands for managing todo categories"""

        addon: Todos

        @app_commands.command(name="list")
        async def todo_category_list(self, interaction: discord.Interaction):
            """List your todo categories"""
            categories = self.addon.bot.profiles[
                interaction.user.id
            ].todo_categories

            embed = neo.Embed(
                description="\n".join(f"• {cat.title()}" for cat in categories)
                if categories
                else "No todo categories"
            ).set_author(
                name=f"{interaction.user}'s todo categories",
                icon_url=interaction.user.display_avatar,
            )
            await interaction.response.send_message(embed=embed)

        @app_commands.command(name="create")
        @app_commands.rename(category_name="category-name")
        @app_commands.describe(category_name="The name of the new category")
        @with_docstring(
            f"Create a new todo category ({MAX_TODO_CATEGORIES} maximum)"
        )
        async def todo_category_create(
            self,
            interaction: discord.Interaction,
            category_name: app_commands.Range[str, 1, MAX_CATEGORY_LEN],
        ):
            profile = self.addon.bot.profiles[interaction.user.id]
            if len(profile.todo_categories) == MAX_TODO_CATEGORIES:
                raise RuntimeError(
                    "You've reached the maximum number of todo categories!"
                )

            _name = category_name.casefold()
            if _name not in profile.todo_categories:
                profile.todo_categories += [_name]
            await send_confirmation(interaction)

        @app_commands.command(name="remove")
        @app_commands.rename(
            category_name="category-name", delete_associated="clear-todos"
        )
        @app_commands.describe(
            category_name="The name of the category to remove",
            delete_associated="Whether todos in this category should be deleted",
        )
        async def todo_category_remove(
            self,
            interaction: discord.Interaction,
            category_name: app_commands.Range[str, 1, MAX_CATEGORY_LEN],
            delete_associated: bool = False,
        ):
            """Remove a todo category"""
            profile = self.addon.bot.profiles[interaction.user.id]
            if category_name not in profile.todo_categories:
                raise ValueError("Invalid category name provided.")

            _name = category_name.casefold()
            if delete_associated:
                query = """
                    DELETE FROM
                        todos
                    WHERE
                        user_id=$1 AND
                        category=$2
                    """
            else:
                query = """
                    UPDATE todos
                    SET category=NULL
                    WHERE
                        user_id=$1 AND
                        category=$2
                    """

            await self.addon.bot.db.execute(query, interaction.user.id, _name)
            for todo in filter(
                lambda t: t.category == _name,
                self.addon.todos[interaction.user.id].copy(),
            ):
                if delete_associated:
                    self.addon.todos[interaction.user.id].remove(todo)
                else:
                    todo.category = None

            # Remove from a shallow copy first
            (categories := profile.todo_categories[:]).remove(_name)
            profile.todo_categories = categories

            await send_confirmation(interaction)

        @todo_category_remove.autocomplete("category_name")
        async def todo_category_remove_autocomplete(
            self, interaction: discord.Interaction, current: str
        ):
            return self.addon._category_autocomplete(interaction, current)


async def setup(bot):
    await bot.add_cog(Todos(bot))

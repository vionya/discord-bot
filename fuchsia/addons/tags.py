# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 sardonicism-04
from __future__ import annotations

from collections import defaultdict
from functools import partial

import asyncpg
import discord
from discord import app_commands

import fuchsia
from fuchsia.classes.app_commands import no_defer
from fuchsia.classes.containers import TimedCache
from fuchsia.tools.checks import is_registered_profile_predicate

TAG_NAME_MIN_LEN = 2
TAG_NAME_MAX_LEN = 100

TAG_CONT_MIN_LEN = 1
TAG_CONT_MAX_LEN = 2000


class TagEditModal(discord.ui.Modal):
    name = discord.ui.TextInput(
        label="Name",
        min_length=TAG_NAME_MIN_LEN,
        max_length=TAG_NAME_MAX_LEN,
        placeholder="The name of this tag",
    )
    content = discord.ui.TextInput(
        label="Content",
        min_length=TAG_CONT_MIN_LEN,
        max_length=TAG_CONT_MAX_LEN,
        placeholder="The content of this tag",
        style=discord.TextStyle.paragraph,
    )
    title = "Edit Tag"

    editing: bool
    response: discord.InteractionResponse

    def __init__(self, *, name: str = "", content: str = "", **kwargs):
        self.name.default = name
        self.content.default = content
        self.editing = (name or content) is not None
        if self.editing:
            self.name.label = "New Name"
            self.content.label = "New Content"
        super().__init__(**kwargs)

    async def on_submit(self, interaction: discord.Interaction):
        self.response = interaction.response


class DeleteAllTagsButton(discord.ui.Button[fuchsia.ButtonsMenu[fuchsia.Pages]]):
    def __init__(self, db: asyncpg.Pool, user_id: int):
        super().__init__(label="Delete all tags", style=discord.ButtonStyle.red, row=0)
        self.db = db
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if not self.view:
            return

        await self.db.execute("DELETE FROM tags WHERE user_id=$1", self.user_id)
        await interaction.response.send_message("Deleted all tags", ephemeral=True)
        self.disabled = True
        await self.view.refresh_page()


class Tags(fuchsia.Addon, app_group=True, group_name="tag"):
    """Commands for managing tags"""

    def __init__(self, bot: fuchsia.Fuchsia):
        self.bot = bot
        self.tags: dict[int, TimedCache[str, str]] = defaultdict(
            partial(TimedCache, timeout=300)
        )
        self.tag_name_cache: TimedCache[int, list[str]] = TimedCache(timeout=30)

        self.bot.tree.context_menu(name="Create Tag")(self.tag_create_ctx_menu)

    async def addon_interaction_check(self, interaction: discord.Interaction) -> bool:
        return await is_registered_profile_predicate(interaction)

    async def getch_tag(self, user_id: int, name: str) -> str | None:
        """
        Gets a tag's content by name, fetching it if necessary

        Returns the tag content if it exists, otherwise returns None
        """
        if name not in self.tags[user_id]:
            tag_content: str | None = await self.bot.db.fetchval(
                """
                SELECT
                    content
                FROM tags
                WHERE
                    user_id=$1 AND
                    name=$2
                """,
                user_id,
                name,
            )
            if not isinstance(tag_content, str):
                return None
            self.tags[user_id][name] = tag_content
        return self.tags[user_id][name]

    async def create_tag(
        self,
        user_id: int,
        response: discord.InteractionResponse,
        name: str,
        content: str,
    ):
        try:
            await self.bot.db.execute(
                """
                INSERT INTO tags (
                    user_id,
                    name,
                    content
                ) VALUES (
                    $1, $2, $3
                ) RETURNING *
                """,
                user_id,
                name,
                content,
            )
            self.tags[user_id][name] = content
            await response.send_message(f"Created a new tag `{name}`", ephemeral=True)
        except asyncpg.UniqueViolationError:
            await response.send_message(
                f"You already have a tag named `{name}`", ephemeral=True
            )

    async def fetch_tag_names(self, user_id: int) -> None:
        """Fetch the tag names of a user, storing it in the internal cache"""
        if user_id not in self.tag_name_cache:
            rows = await self.bot.db.fetch(
                "SELECT name FROM tags WHERE user_id=$1", user_id
            )
            self.tag_name_cache[user_id] = [r["name"] for r in rows]

    @app_commands.command(name="create")
    @no_defer
    async def tag_create(self, interaction: discord.Interaction):
        """Create a new tag"""
        modal = TagEditModal()
        await interaction.response.send_modal(modal)
        if await modal.wait():
            return  # the modal timed out
        await self.create_tag(
            interaction.user.id, modal.response, modal.name.value, modal.content.value
        )

    @app_commands.command(name="get")
    @app_commands.describe(name="The name of the tag to get")
    async def tag_get(
        self,
        interaction: discord.Interaction,
        name: app_commands.Range[str, TAG_NAME_MIN_LEN, TAG_NAME_MAX_LEN],
    ):
        """Get the content of a tag"""
        content = await self.getch_tag(interaction.user.id, name)
        if content is None:
            return await interaction.followup.send(
                f"You have no tag named `{name}`", ephemeral=True
            )
        await interaction.response.send_message(content)

    @app_commands.command(name="list")
    async def tag_list(self, interaction: discord.Interaction):
        """List your existing tags"""
        await self.fetch_tag_names(interaction.user.id)
        pages = fuchsia.Pages(
            [f"`{n}`" for n in self.tag_name_cache[interaction.user.id]] or ["No tags"],
            per_page=25,
            joiner=", ",
            use_embed=True,
            template_embed=fuchsia.Embed().set_author(
                name=f"{interaction.user}'s tags'", url=interaction.user.display_avatar
            ),
        )
        menu = fuchsia.ButtonsMenu(pages)
        menu.add_item(
            DeleteAllTagsButton(
                self.bot.db,
                interaction.user.id,
            )
        )
        await menu.start(interaction)

    @app_commands.command(name="edit")
    @app_commands.describe(name="The name of the tag to edit")
    @no_defer
    async def tag_edit(
        self,
        interaction: discord.Interaction,
        name: app_commands.Range[str, TAG_NAME_MIN_LEN, TAG_NAME_MAX_LEN],
    ):
        """Edit the name and/or content of an existing tag"""
        content = await self.getch_tag(interaction.user.id, name)
        if content is None:
            return await interaction.followup.send(
                f"You have no tag named `{name}`", ephemeral=True
            )
        modal = TagEditModal(name=name, content=content)
        await interaction.response.send_modal(modal)
        if await modal.wait():
            return  # the modal timed out
        new_name = modal.name.value
        new_content = modal.content.value
        response = modal.response
        try:
            await self.bot.db.execute(
                """
                UPDATE tags
                SET
                    name=COALESCE($1, name),
                    content=COALESCE($2, content)
                WHERE
                    user_id=$3 AND
                    name=$4
                """,
                new_name,
                new_content,
                interaction.user.id,
                name,
            )
            self.tags[interaction.user.id].pop(name, None)
            self.tags[interaction.user.id][new_name] = new_content
            await response.send_message("Successfully edited this tag", ephemeral=True)
        except asyncpg.UniqueViolationError:
            await response.send_message(
                "You already have a tag by this name", ephemeral=True
            )

    @app_commands.command(name="delete")
    @app_commands.describe(name="The name of the tag to delete")
    async def tag_delete(
        self,
        interaction: discord.Interaction,
        name: app_commands.Range[str, TAG_NAME_MIN_LEN, TAG_NAME_MAX_LEN],
    ):
        """Delete a tag"""
        was_deleted = await self.bot.db.fetchval(
            "DELETE FROM tags WHERE user_id=$1 AND name=$2 RETURNING true",
            interaction.user.id,
            name,
        )
        if was_deleted is True:
            self.tags[interaction.user.id].pop(name, None)
            return await interaction.response.send_message(
                "Successfully deleted this tag"
            )
        await interaction.response.send_message(
            "There was no tag by this name to delete"
        )

    @tag_get.autocomplete("name")
    @tag_edit.autocomplete("name")
    @tag_delete.autocomplete("name")
    async def tag_name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        if interaction.user.id not in self.bot.profiles:
            return []

        # autocomplete events are debounced by discord, so this isn't too
        # expensive
        await self.fetch_tag_names(interaction.user.id)

        choices = self.tag_name_cache[interaction.user.id]
        return [
            app_commands.Choice(name=n, value=n)
            for n in choices
            if current.casefold() in n.casefold()
        ][:25]

    async def tag_create_ctx_menu(
        self, interaction: discord.Interaction, message: discord.Message
    ):
        """Create a tag from the content of the selected message"""
        if not message.content:
            return await interaction.response.send_message(
                "Message must have content to add it as a tag", ephemeral=True
            )
        modal = TagEditModal(content=message.content)
        await interaction.response.send_modal(modal)
        if await modal.wait():
            return  # the modal timed out
        await self.create_tag(
            interaction.user.id, modal.response, modal.name.value, modal.content.value
        )


async def setup(bot: fuchsia.Fuchsia):
    await bot.add_cog(Tags(bot))

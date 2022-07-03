# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

import asyncio
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Optional,
    TypedDict,
    TypeVar,
    cast,
    final,
    overload,
)

import discord
from neo.classes.app_commands import get_ephemeral
from neo.classes.context import NeoContext
from neo.tools import shorten

from .pages import EmbedPages, Pages

if TYPE_CHECKING:
    from neo import Neo


class SendKwargs(TypedDict):
    content: Optional[str]
    embed: Optional[discord.Embed]
    reference: Optional[discord.MessageReference]


T = TypeVar("T", bound=Pages)


class BaseMenu(Generic[T], discord.ui.View):
    bot: Neo

    __slots__ = (
        "pages",
        "message",
        "interaction",
        "ctx",
        "current_page",
        "running",
        "update_lock",
        "buttons",
        "bot",
        "author",
    )

    def __init__(self, pages: T):
        super().__init__()
        self.pages = pages

        self.message = None
        self.origin: Optional[NeoContext | discord.Interaction] = None
        self.current_page: int = 0
        self.running = False

        self.update_lock = asyncio.Lock()
        self.pages.link(self)

    @classmethod
    def from_iterable(cls, iterable, *, per_page=1, **kwargs):
        _pages = Pages(iterable, per_page, **kwargs)
        return cls(_pages)

    @classmethod
    def from_embeds(cls, iterable, **kwargs):
        _pages = EmbedPages(iterable)
        return cls(_pages, **kwargs)

    @overload
    async def start(self, origin: discord.Interaction):
        ...

    @overload
    async def start(self, origin: NeoContext, *, as_reply=False):
        ...

    async def start(self, origin: NeoContext | discord.Interaction, *, as_reply=False):
        self.origin = origin

        send_kwargs = self._get_msg_kwargs(self.pages[0])

        if isinstance(self.origin, NeoContext):
            # In text commands, menus may optionally be sent as replies
            if as_reply:
                send_kwargs["reference"] = discord.MessageReference(
                    message_id=self.origin.message.id,
                    channel_id=self.origin.channel.id,
                )
            self.message = await self.origin.send(view=self, **send_kwargs)
            self.bot = self.origin.bot
            self.author = self.origin.author

        else:
            await self.origin.response.send_message(view=self, **send_kwargs)
            self.bot = self.origin.client  # type: ignore
            self.author = self.origin.user

        self.running = True

    @final
    def _get_msg_kwargs(self, item) -> dict[str, Any]:
        kwargs = {}

        # If the item is an embed, put the page number in the footer
        if isinstance(item, discord.Embed):
            item.set_footer(text=f"Page {self.current_page + 1}/{len(self.pages)}")
            kwargs["embed"] = item

        # If the item is a string, put the page number at the end of the string
        elif isinstance(item, str):
            item += f"\nPage {self.current_page + 1}/{len(self.pages)}"
            kwargs["content"] = item
        return kwargs

    @final
    def get_current_page(self, index):
        # Logic for when menu is at the first/last page, allows
        # pages to "wrap around"
        if index < 0:
            index = len(self.pages) - 1
        if index > (len(self.pages) - 1):
            index = 0
        self.current_page = index
        return self.pages[index]

    @final
    async def refresh_page(self):
        # Edits the current page with the contents of the
        # stored pages object
        kwargs = self._get_msg_kwargs(self.pages[self.current_page])

        # Interactions need to be handled separately
        if isinstance(self.origin, discord.Interaction):
            if not self.origin.response.is_done():
                await self.origin.response.defer()
            await self.origin.edit_original_message(**kwargs)

        elif self.message:
            await self.message.edit(**kwargs)

    @final
    async def close(
        self, *, interaction: Optional[discord.Interaction] = None, manual=False
    ):
        self.stop()
        self.running = False
        try:
            ephemeral = False
            # Determine whether the menu is being closed in an ephemeral context
            if isinstance(self.origin, discord.Interaction):
                ephemeral = getattr(self.origin.namespace, "ephemeral", False)

            # If closed manually and the message is either a text command or a
            # non-ephemeral slash command, the message can be deleted
            if manual is True and ephemeral is False:
                if isinstance(self.origin, discord.Interaction) and interaction:
                    if not interaction.response.is_done():
                        await interaction.response.defer()
                    await interaction.delete_original_message()

                elif self.message:
                    await self.message.delete()

            # Otherwise, if closed automatically or in an ephemeral
            # context, disable the buttons instead of deleting the message
            else:
                for item in self.children:
                    if isinstance(item, discord.ui.Button | discord.ui.Select):
                        item.disabled = True

                if isinstance(self.origin, discord.Interaction) and interaction:
                    if not interaction.response.is_done():
                        await interaction.response.defer()
                    await interaction.edit_original_message(view=self)

                elif self.message:
                    await self.message.edit(view=self)
        except discord.NotFound:
            return

    @final
    def dispatch_update(self):
        # Dispatches updates to refresh the page without causing race conditions
        async def inner():
            if self.update_lock.locked():
                return

            async with self.update_lock:
                if self.update_lock.locked():
                    await asyncio.sleep(1)

                self.bot.loop.create_task(self.refresh_page())

        self.bot.loop.create_task(inner())

    async def interaction_check(self, interaction):
        # Check that the interaction is valid for affecting the menu
        (predicates := []).append(
            interaction.user.id
            in (self.author.id, *(self.bot.owner_ids or []), self.bot.owner_id)
        )
        return all(predicates)

    @final
    async def on_timeout(self):
        if not self.origin:
            self.stop()
            self.running = False
            return

        if not isinstance(self.origin, discord.Interaction):
            await self.close()
        else:
            await self.close(interaction=self.origin)


class ButtonsMenu(BaseMenu, Generic[T]):
    async def start(self, origin: NeoContext | discord.Interaction, *, as_reply=False):
        interaction = (
            origin
            if isinstance(origin, discord.Interaction)
            else getattr(origin, "interaction", None)
        )

        # If the menu was initiated by an interaction and the interaction is
        # intended to be ephemeral, remove the close button since it's useless
        # (and because it doesn't work in ephemeral contexts)
        if interaction and get_ephemeral(interaction, interaction.namespace) is True:
            self.remove_item(self.close_button)
            await super().start(origin)
            return

        await super().start(origin, as_reply=as_reply)  # type: ignore

    @discord.ui.button(label="ᐊ", row=4)
    async def previous_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        current_page = self.get_current_page(self.current_page - 1)
        send_kwargs = self._get_msg_kwargs(current_page)
        await interaction.response.edit_message(**send_kwargs)

    @discord.ui.button(label="⨉", row=4)
    async def close_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.stop()
        await self.close(interaction=interaction, manual=True)

    @discord.ui.button(label="ᐅ", row=4)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        current_page = self.get_current_page(self.current_page + 1)
        send_kwargs = self._get_msg_kwargs(current_page)
        await interaction.response.edit_message(**send_kwargs)


class DropdownMenuItem(discord.ui.Select):
    def __init__(self, menu: BaseMenu, **kwargs):
        kwargs["placeholder"] = "Choose a page"
        super().__init__(**kwargs)
        self.menu = menu

    async def callback(self, interaction: discord.Interaction):
        current_page = self.menu.get_current_page(int(self.values[0]))
        send_kwargs = self.menu._get_msg_kwargs(current_page)
        await interaction.response.edit_message(**send_kwargs)


class DropdownMenu(ButtonsMenu, Generic[T]):
    @classmethod
    def from_pages(
        cls,
        pages: Pages,
        *,
        embed_auto_label: bool = False,
        embed_auto_desc: bool = False,
    ):
        options: list[discord.SelectOption] = []
        for index, page in enumerate(pages.items, 1):
            label = f"Page {index}"
            description = None

            if isinstance(pages, EmbedPages):
                page = cast(discord.Embed, page)
                if embed_auto_label:
                    label = shorten(page.title or f"Page {index}", 100)
                if embed_auto_desc:
                    description = shorten(page.description or "", 100)

            options.append(
                discord.SelectOption(
                    label=label, value=str(index - 1), description=description
                )
            )

        return cls.from_options(options=options, pages=pages)

    @classmethod
    def from_options(cls, *, options: list[discord.SelectOption], pages: Pages):
        if len(options) > 25:
            raise ValueError("Cannot have more than 25 items")
        instance = cls(pages)

        select = DropdownMenuItem(instance, options=options, row=0)
        instance.add_item(select)

        return instance

    @classmethod
    def from_embeds(cls, *args, **kwargs):
        # This might be something to consider eventually
        raise NotImplementedError

    from_iterable = from_embeds

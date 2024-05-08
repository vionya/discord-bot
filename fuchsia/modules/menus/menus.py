# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 sardonicism-04
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
)

import discord

from fuchsia.classes.context import FuchsiaContext
from fuchsia.tools import shorten

from .pages import EmbedPages, Pages

if TYPE_CHECKING:
    from fuchsia import Fuchsia


class SendKwargs(TypedDict):
    content: Optional[str]
    embed: Optional[discord.Embed]
    reference: Optional[discord.MessageReference]


T = TypeVar("T", bound=Pages)


class BaseMenu(Generic[T], discord.ui.View):
    bot: Fuchsia

    __slots__ = (
        "pages",
        "message",
        "running",
        "update_lock",
        "origin",
        "bot",
        "author",
        "_current_page",
    )

    def __init__(self, pages: T):
        super().__init__()
        self.pages = pages

        self.message = None
        self.origin: Optional[FuchsiaContext | discord.Interaction] = None
        self._page_index: int = 0
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

    async def start(
        self,
        origin: FuchsiaContext | discord.Interaction,
        *,
        as_reply=True,
        force_ephemeral=False,
    ):
        """
        Start this menu at the given origin point

        Origin can be either a `discord.ext.commands.Context`, or a
        `discord.Interaction`. Both origins will generate similarly behaving
        menus.

        :param origin: The location to send the menu to
        :type origin: ``FuchsiaContext | discord.Interaction``

        :param as_reply: Whether the menu's message should reply to the message
        that the context refers to (only applies to `FuchsiaContext` origins)
        :type as_reply: ``bool``

        :param force_ephemeral: Whether menus should be sent ephemerally,
        regardless of user settings (only applies to `Interaction` origins)
        :type force_ephemeral: ``bool``
        """
        self.origin = origin

        send_kwargs = self._get_kwargs(self.pages[0])

        if isinstance(self.origin, FuchsiaContext):
            # In text commands, menus may optionally be sent as replies
            if as_reply:
                send_kwargs["reference"] = discord.MessageReference(
                    message_id=self.origin.message.id,
                    channel_id=self.origin.channel.id,
                )
            self.message = await self.origin.send(**send_kwargs)
            self.bot = self.origin.bot
            self.author = self.origin.author

        else:
            if force_ephemeral is True:
                send_kwargs.update(ephemeral=True)
            await self.origin.response.send_message(**send_kwargs)
            self.bot = self.origin.client  # type: ignore
            self.author = self.origin.user

        self.running = True

    @final
    def _get_kwargs(self, item: str | discord.Embed) -> dict[str, Any]:
        """
        Generates kwargs to update the displayed menu

        Returns a dict containing the menu itself as the view, and an updated
        embed or content.

        :param item: The item to update the displayed menu with
        :type item: ``str | discord.Embed``

        :rtype: ``dict[str, Any]``
        """
        kwargs: dict[str, Any] = {"view": self}

        # If the item is an embed, put the page number in the footer
        if isinstance(item, discord.Embed):
            footer = f"Page {self.page_index + 1}/{len(self.pages)}"
            # if the template embed has a footer then we want to prepend it
            if "footer" in self.pages.template_embed:
                template_footer = self.pages.template_embed["footer"]["text"]
                footer = f"{template_footer.strip()} | {footer}"
            item.set_footer(text=footer)
            kwargs["embed"] = item

        # If the item is a string, put the page number at the end of the string
        elif isinstance(item, str):
            item += f"\nPage {self.page_index + 1}/{len(self.pages)}"
            kwargs["content"] = item
        return kwargs

    @property
    def page_index(self):
        return self._page_index

    @page_index.setter
    def page_index(self, index: int):
        # wraparound
        self._page_index = index % len(self.pages)

    @property
    def current_page(self):
        return self.pages[self.page_index]

    @final
    async def update_page(self, interaction: discord.Interaction):
        """
        Edits the interacted message with the updated contents of the menu

        :param interaction: The interaction to respond to
        :type interaction: ``discord.Interaction``
        """
        await self.on_page_update()
        kwargs = self._get_kwargs(self.current_page)

        await interaction.response.edit_message(**kwargs)

    @final
    async def refresh_page(self):
        """
        Refreshes the displayed content with the value of the internal page
        """
        # Edits the current page with the contents of the
        # stored pages object
        kwargs = self._get_kwargs(self.current_page)

        # Interactions need to be handled separately
        if isinstance(self.origin, discord.Interaction):
            if not self.origin.response.is_done():
                await self.origin.response.defer()
            await self.origin.edit_original_response(**kwargs)

        elif self.message:
            await self.message.edit(**kwargs)

    @final
    async def close(
        self, *, interaction: Optional[discord.Interaction] = None, manual=False
    ):
        self.stop()
        self.running = False
        try:
            # If closed manually, delete the message
            if manual is True:
                if isinstance(self.origin, discord.Interaction) and interaction:
                    if not interaction.response.is_done():
                        await interaction.response.defer()
                    await interaction.delete_original_response()

                elif self.message:
                    await self.message.delete()

            # Otherwise, if closed automatically disable the buttons instead
            # of deleting the message
            else:
                for item in self.children:
                    if isinstance(item, discord.ui.Button | discord.ui.Select):
                        item.disabled = True

                if isinstance(self.origin, discord.Interaction) and interaction:
                    if not interaction.response.is_done():
                        await interaction.response.defer()
                    await interaction.edit_original_response(view=self)

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
                await self.refresh_page()

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

    async def on_page_update(self):
        """
        Define behavior for when a page is updated by user interaction

        This method is called as soon as any menu element makes a call to
        `self.update_page`. It is useful for allowing other menu elements to
        potentially update their state based on the updated state of the menu.

        Intended to be overridden and implemented by subclasses
        """
        ...


class ButtonsMenu(BaseMenu[T]):
    @discord.ui.button(label="ᐊ", row=4)
    async def previous_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.page_index -= 1
        await self.update_page(interaction)

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
        self.page_index += 1
        await self.update_page(interaction)


class DropdownMenuItem(discord.ui.Select):
    def __init__(
        self, menu: BaseMenu, *, options: list[discord.SelectOption], **kwargs
    ):
        kwargs["placeholder"] = "Choose a page"

        self.all_options = options
        kwargs.update(options=options[:25])

        super().__init__(**kwargs)
        self.menu = menu

    async def callback(self, interaction: discord.Interaction):
        self.menu.page_index = int(self.values[0])
        self.update_options_window()
        await self.menu.update_page(interaction)

    def update_options_window(self):
        if len(self.all_options) == 1:
            return
        # guaranteed to exist because this method only called once a selection
        # is made
        cur_index = self.menu.page_index

        len_left = cur_index
        len_right = len(self.all_options) - cur_index - 1

        # current index minus the minimum of the number of elements on the left
        # and (24 - the number of elements on the right if there are less than
        # 12 on the right, otherwise 12)
        slice_start = cur_index - min(
            len_left, 25 - len_right if len_right < 12 else 12
        )
        # current index plus 1 plus the minimum of the number of elements on
        # the right and (24 - the number of elements on the left if there are
        # less than 12 on the left, otherwise 12)
        slice_end = (
            cur_index
            + 1
            + min(len_right, 25 - len_left if len_left < 12 else 12)
        )
        self.options = (
            self.all_options[slice_start:cur_index]
            + self.all_options[cur_index + 1 : slice_end]
        )


class DropdownMenu(ButtonsMenu, Generic[T]):
    select: DropdownMenuItem

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
            page_num = f"Pg {index}"
            label = page_num
            description = None

            if isinstance(pages, EmbedPages):
                page = cast(discord.Embed, page)
                if embed_auto_label:
                    label = shorten(page.title or "…", 100)
                if embed_auto_desc:
                    description = page_num + shorten(
                        " - " + (page.description or "…"), 100 - len(page_num)
                    )

            options.append(
                discord.SelectOption(
                    label=label, value=str(index - 1), description=description
                )
            )

        return cls.from_options(options=options, pages=pages)

    @classmethod
    def from_options(cls, *, options: list[discord.SelectOption], pages: Pages):
        if not all(option.value.isdecimal() for option in options):
            raise TypeError(
                f"{cls.__name__} options must all have integer values"
            )
        instance = cls(pages)

        instance.select = DropdownMenuItem(instance, options=options, row=0)
        instance.add_item(instance.select)

        return instance

    @classmethod
    def from_embeds(cls, *args, **kwargs):
        # This might be something to consider eventually
        raise NotImplementedError

    from_iterable = from_embeds

    async def on_page_update(self):
        # update the select menu to appear around the current page
        self.select.update_options_window()

# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2020-present vionya
from __future__ import annotations

import asyncio
from enum import Flag, auto
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
import logging

from discord import ui
import discord

from fuchsia.classes.context import FuchsiaContext
from fuchsia.tools import shorten

from .pages import EmbedPages, Pages

if TYPE_CHECKING:
    from typing_extensions import Self

    from fuchsia import Fuchsia


class SendKwargs(TypedDict):
    content: Optional[str]
    embed: Optional[discord.Embed]
    reference: Optional[discord.MessageReference]


T = TypeVar("T", bound=Pages)


class Interactors(Flag):
    AUTHOR = auto()
    EVERYONE = auto()
    GUILD_OWNER = auto()
    BOT_OWNER = auto()


class BaseMenu[T: Pages](ui.LayoutView):
    bot: Fuchsia
    pages: T

    __slots__ = (
        "container",
        "pages",
        "message",
        "running",
        "update_lock",
        "origin",
        "bot",
        "author",
        "dm_interactors",
        "private_interactors",
        "guild_interactors",
        "_current_page",
        "_extra_components",
    )

    def __init__(
        self,
        pages: T,
        *,
        dm_interactors: Interactors = Interactors.AUTHOR,
        private_interactors: Interactors = Interactors.AUTHOR,
        guild_interactors: Interactors = Interactors.AUTHOR,
    ):
        super().__init__()
        self.pages = pages
        self.container = ui.Container()
        self.add_item(self.container)

        self.dm_interactors = dm_interactors
        self.private_interactors = private_interactors
        self.guild_interactors = guild_interactors

        self.message = None
        self.origin: Optional[FuchsiaContext | discord.Interaction] = None
        self._page_index: int = 0
        self.running = False

        self.update_lock = asyncio.Lock()
        self.pages.link(self)

        self._extra_components: list[ui.Item] = []

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

        self._update_menu_view(self.pages[0])

        if isinstance(self.origin, FuchsiaContext):
            # In text commands, menus may optionally be sent as replies
            if as_reply:
                self.message = await self.origin.send(
                    view=self,
                    reference=discord.MessageReference(
                        message_id=self.origin.message.id,
                        channel_id=self.origin.channel.id,
                    ),
                )
            else:
                self.message = await self.origin.send(view=self)
            self.bot = self.origin.bot
            self.author = self.origin.author

        else:
            if force_ephemeral is True:
                await self.origin.response.send_message(
                    view=self, ephemeral=True
                )
            else:
                await self.origin.response.send_message(view=self)
            self.bot = self.origin.client  # type: ignore
            self.author = self.origin.user

        self.running = True

    @final
    def _update_menu_view(self, item: str | discord.Embed | ui.Container):
        """
        Generates kwargs to update the displayed menu

        Returns a dict containing the menu itself as the view, and an updated
        embed or content.

        :param item: The item to update the displayed menu with
        :type item: ``str | discord.Embed``

        :rtype: ``dict[str, Any]``
        """
        self.clear_items()
        self.container.clear_items()
        self.update_container(item)
        for component in self._extra_components:
            self.container.add_item(component)
        self.add_item(self.container)

    def update_container(self, item: str | discord.Embed | ui.Container):
        # If the item is an embed, put the page number in the footer
        if isinstance(item, discord.Embed):
            if "title" in self.pages.template_embed:
                self.container.add_item(
                    ui.TextDisplay(f'### {self.pages.template_embed["title"]}')
                )
            self.container.add_item(ui.TextDisplay(item.description or ""))

            # if the template embed has a footer then we want to prepend it
            if "footer" in self.pages.template_embed:
                template_footer = self.pages.template_embed["footer"]["text"]
                self.container.add_item(ui.TextDisplay(f"-# {template_footer}"))

        # If the item is a string, put the page number at the end of the string
        elif isinstance(item, str):
            self.add_item(ui.TextDisplay(item))

        elif isinstance(item, ui.Container):
            self.container = item.copy()

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
        self._update_menu_view(self.current_page)

        await interaction.response.edit_message(view=self)

    @final
    async def refresh_page(self):
        """
        Refreshes the displayed content with the value of the internal page
        """
        # Edits the current page with the contents of the
        # stored pages object
        self._update_menu_view(self.current_page)

        # Interactions need to be handled separately
        if isinstance(self.origin, discord.Interaction):
            if not self.origin.response.is_done():
                await self.origin.response.defer()
            await self.origin.edit_original_response(view=self)

        elif self.message:
            await self.message.edit(view=self)

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
                for item in self.walk_children():
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

    @final
    def _get_interactors_predicate(
        self, interaction: discord.Interaction, interactors: Interactors
    ) -> bool:
        """
        Given an Interactors flag, validates if an interactor is allowed to
        use this menu
        """
        valid_interactors: list[int] = []
        if Interactors.EVERYONE in interactors:
            return True
        if Interactors.AUTHOR in interactors:
            valid_interactors.append(self.author.id)
        if Interactors.BOT_OWNER in interactors:
            if self.bot.owner_ids:
                valid_interactors.extend(self.bot.owner_ids)
            if self.bot.owner_id:
                valid_interactors.append(self.bot.owner_id)
        if Interactors.GUILD_OWNER in interactors and interaction.guild:
            if interaction.guild.owner_id:
                valid_interactors.append(interaction.guild.owner_id)
        return interaction.user.id in valid_interactors

    async def interaction_check(self, interaction: discord.Interaction):
        # Check that the interaction is valid for affecting the menu
        predicates = []

        # an incoming interaction will only have 1 context so elif ladder works
        if interaction.context.guild:
            predicates.append(
                self._get_interactors_predicate(
                    interaction, self.guild_interactors
                )
            )
        elif interaction.context.dm_channel:
            predicates.append(
                self._get_interactors_predicate(
                    interaction, self.dm_interactors
                )
            )
        elif interaction.context.private_channel:
            predicates.append(
                self._get_interactors_predicate(
                    interaction, self.private_interactors
                )
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

    @final
    def add_extra_component(self, component: ui.Item):
        self._extra_components.append(component)


class PageSelectModal(discord.ui.Modal, title="Go to page"):
    page: discord.ui.TextInput[PageSelectModal] = discord.ui.TextInput(
        label="Page number",
        placeholder="1",
        required=True,
        style=discord.TextStyle.short,
    )
    menu: BaseMenu
    index: int | None = None

    def __init__(self, menu: BaseMenu) -> None:
        self.menu = menu
        super().__init__(timeout=30)

    async def on_submit(self, interaction: discord.Interaction, /):
        if not self.page.value.isdecimal():
            return await interaction.response.send_message(
                "You need to provide a valid number", ephemeral=True
            )
        index = int(self.page.value) - 1
        if index < 0 or index > (len(self.menu.pages) - 1):
            return await interaction.response.send_message(
                "The page number must be in the range of the menu",
                ephemeral=True,
            )
        self.menu.page_index = index
        await self.menu.update_page(interaction)


class ButtonsMenuRow(ui.ActionRow):
    __slots__ = ("menu",)

    def __init__(self, menu: BaseMenu):
        super().__init__()
        self.menu = menu
        self.add_item(
            ui.Button(
                label=f"{menu.page_index + 1}/{len(menu.pages)}",
                disabled=True,
            )
        )

    @ui.button(label="ᐊ")
    async def previous_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.menu.page_index -= 1
        await self.menu.update_page(interaction)

    @ui.button(label="⨉")
    async def close_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.menu.stop()
        await self.menu.close(interaction=interaction, manual=True)

    # @ui.button(label="✎")
    # async def page_button(
    #     self, interaction: discord.Interaction, button: discord.ui.Button
    # ):
    #     modal = PageSelectModal(self.menu)
    #     await interaction.response.send_modal(modal)

    @ui.button(label="ᐅ")
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.menu.page_index += 1
        await self.menu.update_page(interaction)


class ButtonsMenu[T: Pages](BaseMenu):
    pages: T

    def update_container(self, item):
        super().update_container(item)
        self.container.add_item(ButtonsMenuRow(self))


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


class DropdownMenu[T: Pages](BaseMenu):
    select: DropdownMenuItem
    pages: T

    @classmethod
    def from_pages(
        cls,
        pages: T,
        *,
        option_labels: list[str] | None = None,
        option_desc: list[str] | None = None,
        **kwargs,
    ):
        if (option_labels and len(option_labels) != len(pages)) or (
            option_desc and len(option_desc) != len(pages)
        ):
            raise ValueError(
                "option labels and descriptions must match page count"
            )

        options: list[discord.SelectOption] = []
        for index, _ in enumerate(pages.items, 1):
            page_num = f"Pg {index}"
            label = (
                page_num
                if not option_labels
                else (shorten(option_labels[index - 1] or "…", 100))
            )
            description = (
                None
                if not option_desc
                else (
                    page_num
                    + shorten(
                        " - " + (option_desc[index - 1] or "…"),
                        100 - len(page_num),
                    )
                )
            )

            options.append(
                discord.SelectOption(
                    label=label, value=str(index - 1), description=description
                )
            )

        return cls.from_options(options=options, pages=pages, **kwargs)

    @classmethod
    def from_options(
        cls, *, options: list[discord.SelectOption], pages: T, **kwargs
    ):
        if not all(option.value.isdecimal() for option in options):
            raise TypeError(
                f"{cls.__name__} options must all have integer values"
            )
        instance = cls(pages, **kwargs)

        instance.select = DropdownMenuItem(instance, options=options)
        # instance.add_item(instance.select)

        return instance

    @classmethod
    def from_embeds(cls, *args, **kwargs):
        # This might be something to consider eventually
        raise NotImplementedError

    from_iterable = from_embeds

    async def on_page_update(self):
        # update the select menu to appear around the current page
        self.select.update_options_window()

    def update_container(self, item: str | discord.Embed):
        super().update_container(item)
        self.container.add_item(ui.ActionRow(self.select))
        self.container.add_item(ButtonsMenuRow(self))

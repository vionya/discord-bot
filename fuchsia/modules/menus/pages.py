# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 sardonicism-04
from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Optional,
    SupportsIndex,
    TypeVar,
    cast,
    final,
)

from discord import Embed as BaseEmbed

from fuchsia.classes import Embed

if TYPE_CHECKING:
    from discord.types.embed import Embed as EmbedData

    from .menus import BaseMenu


class Pages:
    """
    A base class for handling paginated objects.

    Parameters
    ----------

    :param items: The items to be partitioned and paginated
    :type items: ``str | list``

    :param per_page: The number of items to be included on each page, default 1
    :type per_page: ``int``

    :param use_embed: Whether the items should be displayed in a simple embed,
    default False
    :type use_embed: ``bool``

    :param joiner: The string to join items on the page with, default "\\n".
    :type joiner: ``str``

    :param prefix: A string that all pages will be prefixed with, default None.
    May only be used when ``items`` is of type ``str``
    :type prefix: ``str``

    :param suffix: A string that all pages will be suffixed with, default None.
    May only be used when ``items`` is of type ``str``
    :type suffix: ``str``

    :param template_embed: An embed that will be used as a template for all
    pages when `use_embed` is True
    :type template_embed: ``discord.Embed``

    Attributes
    ----------

    :property pages: Returns the partitioning of all pages
    :type pages: ``list``
    """

    __slots__ = (
        "items",
        "joiner",
        "per_page",
        "use_embed",
        "prefix",
        "suffix",
        "template_embed",
        "menu",
        "_old_page_count",
    )

    def __init__(
        self,
        items: str | list,
        /,
        per_page: int = 1,
        *,
        use_embed: bool = False,
        joiner: str = "\n",
        prefix: str = "",
        suffix: str = "",
        template_embed: Optional[Embed] = None,
    ):
        if not isinstance(items, str | list):
            raise TypeError('"items" must be of type list or str')

        self.items = items
        self.joiner = joiner
        self.per_page = per_page
        self.use_embed = use_embed
        self.menu: Optional[BaseMenu] = None

        if (prefix or suffix) and not isinstance(items, str):
            raise TypeError(
                'Arguments "prefix" and "suffix" may only be used in conjunction with an input of type str'
            )
        self.prefix = prefix
        self.suffix = suffix
        self.template_embed: EmbedData = {}
        if template_embed is not None:
            self.template_embed = template_embed.to_dict()

    def __repr__(self):
        return "<{0.__class__.__name__} pages={1}>".format(
            self, len(self.pages)
        )

    @final
    def link(self, menu: BaseMenu):
        self.menu = menu

    @final
    def _split_pages(self):
        _items = self.items
        _pages = []
        while _items:

            if (self.suffix or self.prefix) and isinstance(_items, str):
                to_append = self.prefix + _items[: self.per_page] + self.suffix

            else:
                to_append = _items[: self.per_page]
            _pages.append(to_append)
            _items = _items[self.per_page :]

        return _pages

    @property
    def pages(self):
        return self._split_pages()

    def __getitem__(self, index: SupportsIndex):
        content = self.joiner.join(self.pages[index])
        if self.use_embed:
            return Embed.from_dict(
                cast(dict, self.template_embed | {"description": content})
            )
        return content

    @final
    def append(self, new: Any):
        self._old_page_count = len(self.pages)

        if isinstance(self.items, str) and isinstance(new, str):
            self.items += new
        elif isinstance(self.items, list):
            self.items.append(new)

        if self.menu and self.menu.running is True:
            self.menu.dispatch_update()

    @final
    def prepend(self, new: Any):
        self._old_page_count = len(self.pages)

        if isinstance(self.items, str) and isinstance(new, str):
            self.items = new + self.items
        elif isinstance(self.items, list):
            self.items.insert(0, new)

        if self.menu and self.menu.running is True:
            self.menu.dispatch_update()

    def __len__(self):
        return len(self.pages)


T = TypeVar("T", bound=BaseEmbed)


class EmbedPages(Pages, Generic[T]):
    """
    A subclass of Pages that takes an iterable of Embeds as its input.
    """

    items: list[T]

    def __init__(self, items: list[T]):
        super().__init__(items, 1)

    @property
    def pages(self):
        return self.items

    def __getitem__(self, index: SupportsIndex):
        return self.pages[index]

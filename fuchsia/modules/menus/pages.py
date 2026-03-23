# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2020-present vionya
from __future__ import annotations

from math import ceil
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
from discord import ui

from fuchsia.classes import Embed

if TYPE_CHECKING:
    from discord.types.embed import Embed as EmbedData

    from .menus import BaseMenu


class Pages:
    """
    A base class for handling paginated objects.

    This is a lazy view of the internal items, and computes pages as-needed,
    avoiding storing chunked pages in memory.

    Pages are accessed via ``__getitem__``.

    Parameters
    ----------

    :param items: The items to be partitioned and paginated
    :type items: ``str | list``

    :param per_page: The number of items to be included on each page, default 1
    :type per_page: ``int``

    :param use_container: Whether the items should be displayed in a simple container,
    default False
    :type use_container: ``bool``

    :param joiner: The string to join items on the page with, default "\\n".
    :type joiner: ``str``

    :param prefix: A string that all pages will be prefixed with, default None.
    May only be used when ``items`` is of type ``str``
    :type prefix: ``str``

    :param suffix: A string that all pages will be suffixed with, default None.
    May only be used when ``items`` is of type ``str``
    :type suffix: ``str``

    :param template_embed: An embed that will be used as a template for all
    pages when `use_container` is True
    :type template_embed: ``discord.Embed``
    """

    __slots__ = (
        "items",
        "joiner",
        "per_page",
        "use_container",
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
        use_container: bool = False,
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
        self.use_container = use_container
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
        return "<{0.__class__.__name__} pages={1}>".format(self, len(self))

    @final
    def link(self, menu: BaseMenu):
        self.menu = menu

    @final
    def _compute_page(self, index: int) -> str | list[str]:
        """
        Computes the value of the page at the given index

        :param index: the index of the page to get
        :type index: ``int``
        """
        actual_index = index * self.per_page
        page = self.items[actual_index : (actual_index + self.per_page)]
        if (self.suffix or self.prefix) and isinstance(page, str):
            return self.prefix + page + self.suffix
        else:
            return page

    def __getitem__(self, index: SupportsIndex) -> str | BaseEmbed:
        content = self.joiner.join(self._compute_page(int(index)))
        if self.use_container:
            return Embed.from_dict(
                cast(dict, self.template_embed | {"description": content})
            )
        return content

    @final
    def append(self, new: Any):
        self._old_page_count = len(self)

        if isinstance(self.items, str) and isinstance(new, str):
            self.items += new
        elif isinstance(self.items, list):
            self.items.append(new)

        if self.menu and self.menu.running is True:
            self.menu.dispatch_update()

    @final
    def prepend(self, new: Any):
        self._old_page_count = len(self)

        if isinstance(self.items, str) and isinstance(new, str):
            self.items = new + self.items
        elif isinstance(self.items, list):
            self.items.insert(0, new)

        if self.menu and self.menu.running is True:
            self.menu.dispatch_update()

    def __len__(self) -> int:
        return ceil(len(self.items) / self.per_page)


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

    def __getitem__(self, index: SupportsIndex) -> BaseEmbed:
        return self.pages[index]


class ContainerPages(Pages):
    items: list[ui.Container]

    def __init__(self, items: list[ui.Container]):
        super().__init__(items, 1)

    @property
    def pages(self):
        return self.items

    def __getitem__(self, index: SupportsIndex) -> ui.Container:
        return self.pages[index]
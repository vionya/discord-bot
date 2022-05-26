# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

import asyncio
import zoneinfo
from abc import ABCMeta, abstractmethod
from collections.abc import MutableMapping, MutableSet
from functools import cache
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import datetime


def add_hook(attr_name: str):
    """
    Registers this method as a hook for the given attribute.

    This hook will be called whenever the attribute is accessed.

    Parameters
    ----------
    attr_name: str
        The attribute which is to be hooked

    Returns
    -------
    Any
        The decorated method must return a type. Usually, this is
        a transformed version of the original attribute
    """
    def inner(func):
        setattr(func, "_hooks_to", attr_name)
        return func
    return inner


class RecordContainer(metaclass=ABCMeta):
    """
    Provides an OOP interface for getting data from and updating a database record
    """

    __slots__ = ("ready", "pool", "hooks", "_data")

    def __init__(self, *, pool, **record):
        super().__setattr__("ready", False)
        super().__setattr__("pool", pool)

        for key, value in record.items():
            setattr(self, key, value)

        super().__setattr__("ready", True)

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        object.__setattr__(instance, "hooks", {})

        for name in dir(instance):
            attr = getattr(instance, name, None)
            if hasattr(attr, "_hooks_to"):
                instance.hooks[attr._hooks_to] = attr

        object.__setattr__(instance, "ready", True)
        return instance

    def __repr__(self):
        return "<{0.__class__.__name__}>".format(self)

    def __setattr__(self, attribute, value):
        if attribute not in self.__slots__:
            raise AttributeError("{0.__class__.__name__!r} object has no attribute {1!r}".format(
                self, attribute))

        if getattr(self, "ready", False):
            asyncio.create_task(self.update_relation(attribute, value))

        super().__setattr__(attribute, value)

    def __getattribute__(self, attribute):
        value = object.__getattribute__(self, attribute)
        if (hook := object.__getattribute__(self, "hooks").get(attribute)):
            value = hook(value)
        return value

    @abstractmethod
    async def update_relation(self, attribute, value):
        ...

    @abstractmethod
    async def reset_attribute(self, attribute):
        """
        Resets the value of an attribute to its database default.
        """
        ...


class NeoUser(RecordContainer):
    user_id: int
    hl_blocks: list[int]
    receive_highlights: bool
    created_at: datetime.datetime
    timezone: Optional[zoneinfo.ZoneInfo]
    hl_timeout: int
    default_ephemeral: bool

    __slots__ = (
        "user_id",
        "hl_blocks",
        "receive_highlights",
        "created_at",
        "timezone",
        "hl_timeout",
        "default_ephemeral"
    )

    def __repr__(self):
        return "<{0.__class__.__name__} user_id={0.user_id}>".format(self)

    @add_hook("timezone")
    @cache
    def cast_timezone(self, timezone: str | None = None) -> zoneinfo.ZoneInfo | None:
        if timezone is not None:
            return zoneinfo.ZoneInfo(timezone)
        return None

    async def update_relation(self, attribute, value):
        await self.pool.execute(
            f"""
            UPDATE profiles
            SET
                {attribute}=$1
            WHERE
                user_id=$2
            """,    # While it isn't ideal to use string formatting with SQL,
            value,  # the class implements __slots__, so possible attribute names are restricted
            self.user_id
        )

    async def reset_attribute(self, attribute):
        if attribute not in self.__slots__:
            raise AttributeError("{0.__class__.__name__!r} object has no attribute {1!r}".format(
                self, attribute))

        value = await self.pool.fetchval(
            f"""
            UPDATE profiles
            SET
                {attribute}=DEFAULT
            WHERE
                user_id=$1
            RETURNING
                {attribute}
            """,
            self.user_id
        )
        super().__setattr__(attribute, value)


class NeoGuildConfig(RecordContainer):
    guild_id: int
    prefix: str
    starboard: bool
    disabled_channels: list[int]
    disabled_commands: list[str]

    __slots__ = ("guild_id", "prefix", "starboard", "disabled_channels", "disabled_commands")

    def __repr__(self):
        return "<{0.__class__.__name__} guild_id={0.guild_id}>".format(self)

    async def update_relation(self, attribute, value):
        await self.pool.execute(
            f"""
            UPDATE guild_configs
            SET
                {attribute}=$1
            WHERE
                guild_id=$2
            """,    # While it isn't ideal to use string formatting with SQL,
            value,  # the class implements __slots__, so possible attribute names are restricted
            self.guild_id
        )

    async def reset_attribute(self, attribute):
        if attribute not in self.__slots__:
            raise AttributeError("{0.__class__.__name__!r} object has no attribute {1!r}".format(
                self, attribute))

        value = await self.pool.fetchval(
            f"""
            UPDATE guild_configs
            SET
                {attribute}=DEFAULT
            WHERE
                guild_id=$1
            RETURNING
                {attribute}
            """,
            self.guild_id
        )
        super().__setattr__(attribute, value)


class TimedSet(MutableSet):
    __slots__ = ("__underlying_set__", "__running_store__", "loop", "timeout")

    def __init__(self, *args, timeout: int = 60, loop: Optional[asyncio.AbstractEventLoop] = None):
        self.timeout = timeout
        self.loop = loop or asyncio.get_event_loop()

        self.__underlying_set__ = set()
        self.__running_store__: dict[str, asyncio.tasks.Task] = {}

        for element in args:
            self.add(element)

    async def invalidate(self, element):
        await asyncio.sleep(self.timeout)
        self.discard(element)

    def add(self, element):
        if element in self:
            active = self.__running_store__.pop(element)
            active.cancel()

        self.__underlying_set__.add(element)
        self.__running_store__[element] = self.loop.create_task(self.invalidate(element))

    def discard(self, element):
        self.__running_store__[element].cancel()
        del self.__running_store__[element]
        self.__underlying_set__.discard(element)

    def clear(self):
        for task in self.__running_store__.values():
            task.cancel()
        self.__underlying_set__.clear()

    def __contains__(self, o: object) -> bool:
        return self.__underlying_set__.__contains__(o)

    def __iter__(self):
        return iter(self.__underlying_set__)

    def __len__(self):
        return len(self.__underlying_set__)


class TimedCache(MutableMapping):
    __slots__ = ("__dict__", "__running_store__", "loop", "timeout")

    def __init__(self, timeout: int = 60, loop: Optional[asyncio.AbstractEventLoop] = None, **kwargs):
        self.timeout = timeout
        self.loop = loop or asyncio.get_event_loop()

        self.__running_store__: dict[str, asyncio.tasks.Task] = {}

        for k, v in kwargs.items():
            self[k] = v

    async def invalidate(self, key):
        await asyncio.sleep(self.timeout)
        del self[key]

    def clear(self):
        for task in self.__running_store__.values():
            task.cancel()
        self.__dict__.clear()

    def __setitem__(self, key, value):
        if key in self:
            active = self.__running_store__.pop(key)
            active.cancel()

        self.__dict__[key] = value
        self.__running_store__[key] = self.loop.create_task(self.invalidate(key))

    def __getitem__(self, key):
        return self.__dict__[key]

    def __delitem__(self, key):
        self.__running_store__[key].cancel()
        del self.__running_store__[key]
        del self.__dict__[key]

    def __iter__(self):
        return iter(self.__dict__)

    def __len__(self):
        return len(self.__dict__)

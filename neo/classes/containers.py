# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
from __future__ import annotations

import asyncio
import zoneinfo
from abc import ABCMeta, abstractmethod
from collections.abc import Mapping, MutableMapping, MutableSet
from functools import cache
from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar

from neo.tools import humanize_snake_case

if TYPE_CHECKING:
    import datetime

    from typing_extensions import Never, Unpack

    from neo.types.settings_mapping import SettingData


def add_hook(attr_name: str):
    """
    Registers this method as a hook for the given attribute.

    This hook will be called whenever the attribute is accessed.

    :param attr_name: The attribute which is to be hooked
    :type attr_name: ``str``

    :returns: The decorated method
    """

    def inner(func):
        setattr(func, "_hooks_to", attr_name)
        return func

    return inner


class RecordContainer(metaclass=ABCMeta):
    """
    Provides an OOP interface for getting data from and updating a database record
    """

    __slots__ = ("ready", "pool", "hooks")

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
            raise AttributeError(
                "{0.__class__.__name__!r} object has no attribute {1!r}".format(
                    self, attribute
                )
            )

        if getattr(self, "ready", False):
            asyncio.create_task(self.update_relation(attribute, value))

        super().__setattr__(attribute, value)

    def __getattribute__(self, attribute):
        value = object.__getattribute__(self, attribute)
        if hook := object.__getattribute__(self, "hooks").get(attribute):
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
    silence_hl: bool
    reminders_in_channel: bool

    __slots__ = (
        "user_id",
        "hl_blocks",
        "receive_highlights",
        "created_at",
        "timezone",
        "hl_timeout",
        "default_ephemeral",
        "silence_hl",
        "reminders_in_channel",
    )

    def __repr__(self):
        return "<{0.__class__.__name__} user_id={0.user_id}>".format(self)

    @add_hook("timezone")
    @cache
    def cast_timezone(
        self, timezone: str | None = None
    ) -> zoneinfo.ZoneInfo | None:
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
            """,  # While it isn't ideal to use string formatting with SQL,
            value,  # the class implements __slots__, so possible attribute names are restricted
            self.user_id,
        )

    async def reset_attribute(self, attribute):
        if attribute not in self.__slots__:
            raise AttributeError(
                "{0.__class__.__name__!r} object has no attribute {1!r}".format(
                    self, attribute
                )
            )

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
            self.user_id,
        )
        super().__setattr__(attribute, value)


class NeoGuildConfig(RecordContainer):
    guild_id: int
    starboard: bool
    disabled_channels: list[int]
    disabled_commands: list[str]

    __slots__ = (
        "guild_id",
        "starboard",
        "disabled_channels",
        "disabled_commands",
        "allow_highlights",
    )

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
            """,  # While it isn't ideal to use string formatting with SQL,
            value,  # the class implements __slots__, so possible attribute names are restricted
            self.guild_id,
        )

    async def reset_attribute(self, attribute):
        if attribute not in self.__slots__:
            raise AttributeError(
                "{0.__class__.__name__!r} object has no attribute {1!r}".format(
                    self, attribute
                )
            )

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
            self.guild_id,
        )
        super().__setattr__(attribute, value)


T = TypeVar("T")


class TimedSet(MutableSet, Generic[T]):
    __slots__ = ("__underlying_set", "__running_store", "loop", "timeout")

    def __init__(
        self,
        *args: T,
        timeout: int = 60,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self.timeout = timeout
        self.loop = loop or asyncio.get_event_loop()

        self.__underlying_set: set[T] = set()
        self.__running_store: dict[T, asyncio.tasks.Task[None]] = {}

        for element in args:
            self.add(element)

    async def invalidate(self, element: T):
        await asyncio.sleep(self.timeout)
        self.discard(element)

    def add(self, element: T):
        if element in self:
            active = self.__running_store.pop(element)
            active.cancel()

        self.__underlying_set.add(element)
        self.__running_store[element] = self.loop.create_task(
            self.invalidate(element)
        )

    def discard(self, element: T):
        self.__running_store[element].cancel()
        del self.__running_store[element]
        self.__underlying_set.discard(element)

    def clear(self):
        for task in self.__running_store.values():
            task.cancel()
        self.__underlying_set.clear()

    def __contains__(self, o: T) -> bool:
        return self.__underlying_set.__contains__(o)

    def __iter__(self):
        return iter(self.__underlying_set)

    def __len__(self):
        return len(self.__underlying_set)


KT = TypeVar("KT")
VT = TypeVar("VT")


class TimedCache(MutableMapping, Generic[KT, VT]):
    __slots__ = ("_store", "loop", "timeout")

    loop: asyncio.AbstractEventLoop
    timeout: int
    _store: dict[KT, tuple[asyncio.tasks.Task[None], VT]]

    def __init__(
        self,
        timeout: int = 60,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self.timeout = timeout
        self.loop = loop or asyncio.get_event_loop()

        self._store = {}

    async def invalidate(self, key: KT):
        await asyncio.sleep(self.timeout)
        del self[key]

    def clear(self):
        for task, _ in self._store.values():
            task.cancel()
        self._store.clear()

    def __setitem__(self, key: KT, value: VT):
        if key in self:
            active = self._store.pop(key)[0]
            active.cancel()

        self._store[key] = (self.loop.create_task(self.invalidate(key)), value)

    def __getitem__(self, key: KT):
        return self._store[key][1]

    def __delitem__(self, key: KT):
        self._store[key][0].cancel()
        del self._store[key]

    def __iter__(self):
        return iter(self._store)

    def __len__(self):
        return len(self._store)


class Setting(MutableMapping):
    __slots__ = ("__setting_key", "__setting_data")

    def __init__(self, key: str, /, **data: Unpack[SettingData]):
        self.__setting_key = key

        if "description" not in data:
            data["description"] = None
        self.__setting_data = data

    @property
    def display_name(self) -> str:
        if "name_override" in self:
            return self["name_override"]
        else:
            return humanize_snake_case(self.__setting_key)

    @property
    def key(self) -> str:
        return self.__setting_key

    def __getitem__(self, key: str):
        return self.__setting_data[key]

    def __setitem__(self, key: str, value: Any):
        self.__setting_data[key] = value

    def __delitem__(self, key: Never):
        raise NotImplementedError

    def __iter__(self):
        return iter(self.__setting_data)

    def __len__(self):
        return len(self.__setting_data)


class SettingsMapping(Mapping):
    __slots__ = ("__settings_data",)

    __settings_data: dict[str, Setting]

    def __init__(self, *items: Setting):
        self.__settings_data = {item.key: item for item in items}

    def __getitem__(self, key: str):
        return self.__settings_data[key]

    def __iter__(self):
        return iter(self.__settings_data)

    def __len__(self) -> int:
        return len(self.__settings_data)

    def items(self):
        return self.__settings_data.items()

    def keys(self):
        return self.__settings_data.keys()

    def values(self):
        return self.__settings_data.values()

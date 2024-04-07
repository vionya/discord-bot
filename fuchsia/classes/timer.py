# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 sardonicism-04
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ..tools.formatters import format_exception

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class PeriodicTimer:
    """
    Implements simple async periodicity with a coroutine callback

    Note on execution order:
    ```txt
    self.start() called -> ↱   callback called once    ⮧
                           ⮤ wait for interval seconds ↲
    ```
    """

    __slots__ = (
        "callback",
        "interval",
        "instance",
        "is_stopped",
        "logger",
        "task",
    )

    def __init__(self, callback: Callable[..., Awaitable[None]], interval: int):
        self.callback = callback
        self.interval = interval
        self.instance = None
        self.is_stopped = False
        self.logger = logging.getLogger(callback.__module__)

    def __get__(self, instance: object | None, cls):
        if instance is None:
            return self

        self.instance = instance
        return self

    def start(self):
        self.task = asyncio.create_task(self.runner())

    def shutdown(self):
        if not self.task.done():
            self.is_stopped = True

    def cancel(self):
        if not self.task.done():
            self.task.cancel()

    async def runner(self):
        while True:
            try:
                if self.instance:
                    await self.callback(self.instance)
                else:
                    await self.callback()
            except BaseException as e:
                self.logger.error(format_exception(e))
            if self.is_stopped:
                self.cancel()
            await asyncio.sleep(self.interval)


def periodic(interval: int = 60):
    """Creates a `PeriodicTimer` that wraps the decorated function"""

    def inner(func: Callable[..., Awaitable[None]]) -> PeriodicTimer:
        return PeriodicTimer(func, interval)

    return inner

# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 sardonicism-04
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, TypeVar, overload
from discord.app_commands import Command, Group, ContextMenu

if TYPE_CHECKING:
    from collections.abc import Callable


T = TypeVar("T")


def singleton(cls: type[T]) -> T:
    """
    Decorates a class definition, creating an eagerly-evaluated singleton

    ```py
    class Foo:
        @singleton
        class Bar:
            pass

    # Foo.Bar is now an instantiated Bar singleton
    ```
    """
    return cls()


@overload
def deprecate(*, reason: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...


@overload
def deprecate(func: Callable[..., Any]) -> Callable[..., Any]: ...


def deprecate(
    func: Optional[Callable[..., Any]] = None,
    *,
    reason: Optional[str] = None,
) -> Callable[..., Any] | Callable[[Callable[..., Any]], Callable[..., Any]]:
    if func is not None:
        setattr(func, "_deprecated", True)
        return func

    def inner(func: Callable[..., Any]) -> Callable[..., Any]:
        setattr(func, "_deprecated", reason)
        return func

    return inner


def with_docstring(docstring: str) -> Callable[[Callable[..., Any]], Any]:
    """Dynamically set a function's doc string"""

    def inner(func: Callable[..., Any]) -> Callable[..., Any]:
        func.__doc__ = docstring
        return func

    return inner

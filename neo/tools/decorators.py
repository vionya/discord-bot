# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

from typing import Any, Callable, Optional, TypeVar, overload

T = TypeVar("T")


def instantiate(cls: type[T]) -> T:
    """Instantiates a class, allowing it to be accessed as an instance in the class's type attributes

    ```py
    class Foo:
        @instantiate
        class Bar:
            pass

    # Foo.Bar is now an instantiated Bar
    ```
    """
    return cls()


@overload
def deprecate(*, reason: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    ...


@overload
def deprecate(func: Callable[..., Any]) -> Callable[..., Any]:
    ...


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


def no_defer(callback: Callable[..., Any]) -> Callable[..., Any]:
    """Decorates a callback, preventing the app command from being automatically deferred"""
    setattr(callback, "no_defer", True)
    return callback

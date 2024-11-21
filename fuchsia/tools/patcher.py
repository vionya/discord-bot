# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 vionya
from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Optional, overload

if TYPE_CHECKING:
    from collections.abc import Callable


class Patcher:
    """
    Utility class to facilitate monkeypatching... stuff

    Initialise class with a target, which can be a module, or a class, etc
    """

    __slots__ = ("targets", "_patches", "_original")

    def __init__(self, *targets: Any):
        self.targets = targets
        self._patches: dict[str, Any] = {}
        self._original: dict[str, dict[str, Any]] = defaultdict(dict)

        for target in self.targets:
            for name, attr in map(
                lambda _attr: (_attr, getattr(target, _attr)), dir(target)
            ):
                self._original[target.__name__][name] = attr

    @overload
    def attribute(self, *, value: Any, name: Optional[str]) -> None:
        ...

    @overload
    def attribute(self) -> Callable[[Callable[..., Any]], None]:
        ...

    @overload
    def attribute(self, *, name: str) -> Callable[[Callable[..., Any]], None]:
        ...

    def attribute(
        self, *, value=None, name=None
    ) -> Callable[[Callable[..., Any]], None] | None:
        """
        Patch an attribute onto the target.

        This method can be used as a normal function or as a decorator.

        If `value` is given, then that value will be patched, under
        the name parameter, or its __name__ value

        This can also be used to decorate a function or a class.
        It can be used to add methods to classes, classes to modules, etc.

        Note that by itself, this method only stores the new attribute
        internally. The patch() method applies the patch itself.
        """
        if value is not None:
            self._patches[name or getattr(value, "__name__", name)] = value  # type: ignore
            return

        def inner(attr: Callable[..., Any]):
            self._patches[name or getattr(attr, "__name__", name)] = attr  # type: ignore

        return inner

    def patch(self):
        """
        Applies all staged patches to the target.
        """
        for name, attr in self._patches.items():
            for target in self.targets:
                setattr(target, name, attr)

    def revert(self):
        """
        Reverts the target back to its state at the time that the
        Patcher was instantiated.

        Any *new* attributes will be removed, and all overridden
        attributes will be reverted.
        """
        for target in self.targets:
            for name in self._patches.keys():
                delattr(target, name)
            for name, attr in self._original.items():
                try:
                    setattr(target, name, attr)
                except (TypeError, AttributeError):
                    continue

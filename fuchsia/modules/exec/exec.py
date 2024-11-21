# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 vionya
from __future__ import annotations

from inspect import isasyncgenfunction, iscoroutinefunction
from typing import TYPE_CHECKING, Any

from .compiler import compile_all

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Coroutine

    AExecType = Callable[
        [dict[str, Any]], Coroutine[Any, Any, Any] | AsyncGenerator[Any, Any]
    ]


class ExecWrapper:
    __slots__ = ("compiled", "globals_", "locals_")

    def __init__(
        self,
        code_input: str,
        globals_: dict[str, Any] = {},
        locals_: dict[str, Any] = {},
    ):
        self.compiled = compile_all(code_input)
        self.globals_ = globals_
        self.locals_ = locals_

    def __aiter__(self):
        exec_locals: dict[str, Any] = {}
        exec(
            compile(self.compiled, "<exec>", "exec"), self.globals_, exec_locals
        )
        _aexec: AExecType = exec_locals["__aexec__"]
        return self.walk_results(_aexec, self.locals_)

    async def walk_results(self, coro: AExecType, scope: dict[str, Any]):
        try:
            if isasyncgenfunction(coro):
                async for result in coro(scope):
                    yield result
            else:
                assert iscoroutinefunction(coro)
                yield await coro(scope)

        finally:
            if "scope" in self.locals_:
                del self.locals_["scope"]

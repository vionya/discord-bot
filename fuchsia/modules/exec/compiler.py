# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
import ast

BASE_CODE = (
    "async def __aexec__(scope):"
    "\n    try:"
    "\n        pass"
    "\n    finally:"
    "\n        scope |= locals()"
)


def insert_yield(body: list[ast.stmt]):
    if not isinstance(body[-1], ast.Expr):
        # If the last item in the injected code is not an expression, nothing
        # needs to be done
        return

    if not isinstance(body[-1].value, ast.Yield):
        # If the last item is an expression, we replace it with a yield
        # statement that yields the value of the expression

        # Create a yield expression wrapping the expression
        yield_st = ast.Yield(body[-1].value)
        # Wrap the yield expression in its own expression
        yield_expr = ast.Expr(yield_st)
        # Replace the final expression in the code body with the new wrapped
        # yield expression
        body[-1] = yield_expr


def compile_all(code_input: str):
    code_in = ast.parse(code_input)
    base = ast.parse(BASE_CODE)

    # These 2 asserts are guaranteed by the definition of `BASE_CODE`
    assert isinstance(base.body[-1], ast.AsyncFunctionDef)
    assert isinstance(base.body[-1].body[-1], ast.Try)

    # Get the list of statements inside the try block
    inject_at = base.body[-1].body[-1].body
    # Extend these statements with the body of the parsed input
    inject_at.extend(code_in.body)

    # Replace the final injected element with a yield if it is an expression
    insert_yield(inject_at)
    # Fix all missing locations
    ast.fix_missing_locations(base)

    return base

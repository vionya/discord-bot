# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from argparse import ArgumentError, ArgumentParser

from discord.ext.commands import (
    CommandError,
    Converter,
    MissingRequiredArgument
)


class MockParam(str):
    @property
    def name(self):
        return str(self)


class Parser(ArgumentParser):
    def __init__(self, *args, **kwargs):
        self.ctx = None
        kwargs.setdefault("add_help", False)
        super().__init__(*args, **kwargs)

    def error(self, message, _error=CommandError):
        if message.startswith("the following arguments are required"):
            _error = MissingRequiredArgument
            message = MockParam(message.split(": ")[-1])
        raise _error(message)

    def _get_value(self, action, arg_string):
        converter = self._registry_get("type", action.type, action.type)

        if not callable(converter):
            msg = "%r is not callable"
            raise ArgumentError(action, msg % converter)

        if isinstance(converter, type) and issubclass(converter, Converter):
            return converter().convert(self.ctx, arg_string)
            # Above tries to return an awaitable from a converter

        try:
            return converter(arg_string)
        except ValueError:
            self.error(f"Bad value type for flag argument `{action.dest}`"
                       f" (expected type: `{converter.__name__}`)")
        except Exception as e:
            self.error(str(e))

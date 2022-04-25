# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
import shlex
from inspect import isawaitable

import discord
from discord.ext import commands

from .parser import Parser


class ArgCommand(commands.Command):

    @property
    def signature(self):
        if self.usage is not None:
            return self.usage

        args = []
        for arg in reversed(self.callback.parser._actions):
            argname = f"--{arg.dest}" if arg.option_strings else arg.dest

            if arg.choices:
                argname += " [{}]".format("|".join(arg.choices))

            if arg.required:
                argname = f"<{argname}>"
            else:
                argname = f"[{argname}]"

            args.append(argname)

        return " ".join(args)

    def get_args_help(self):
        for arg in reversed(self.callback.parser._actions):
            if not hasattr(arg, "dest"):  # Logically this shouldn't happen
                continue

            argname = f"--{arg.dest}" if arg.option_strings else arg.dest
            description = getattr(arg, "help", None)

            if len(arg.option_strings) > 1:
                aliases = ", ".join(arg.option_strings)
                description += f"\n↳ **Flag Aliases** {aliases}"

            converter = self.callback.parser._registry_get(
                "type", arg.type, arg.type)
            if converter.__name__ != "identity":
                description += f"\n↳ **Expected type** `{converter.__name__}`"

            if arg.default:
                description += f"\n↳ **Default** `{arg.default}`"

            yield (argname, description)

    async def _parse_arguments(self, ctx):
        self.callback.parser.ctx = ctx

        ctx.args = [ctx] if self.cog is None else [self.cog, ctx]
        ctx.kwargs = {}

        kwargs = ctx.kwargs
        view = ctx.view
        iterator = iter(self.params.items())

        if self.cog is not None:
            fmt = "Callback for {0.name} must contain one keyword-only argument."
            try:
                name, param = next(iterator)
                if param.kind != param.KEYWORD_ONLY:
                    raise discord.ClientException(fmt.format(self))

                to_parse = view.read_rest().strip()
                if to_parse is None:
                    kwargs[name] = None
                    return

                try:
                    to_parse = shlex.split(to_parse, " ", posix=False)
                    parsed = self.callback.parser.parse_args(to_parse)
                except Exception:
                    kwargs[name] = None
                    raise

                try:
                    for k, v in vars(parsed).items():
                        if not isinstance(v, list):
                            if isawaitable(v):
                                vars(parsed)[k] = await v
                            continue

                        values = []
                        for result in v:
                            if isawaitable(result):
                                values.append(await result)
                                continue

                            values.append(result)
                        vars(parsed)[k] = values

                    kwargs[name] = parsed

                except Exception:
                    coros = []
                    for v in vars(parsed).values():
                        if isawaitable(v):
                            coros.append(v)
                            continue

                        if isinstance(v, list):
                            coros.extend([*filter(lambda r: isawaitable(r), v)])

                    for coro in coros:
                        coro.close()  # Cleanup awaitables that will be abandoned
                    raise

            except StopIteration:
                raise discord.ClientException(fmt.format(self))


def add_arg(*args, **kwargs):
    """
    Add an argument to this command's arguments.

    Parameters are just those of argparse's parser.add_argument.

    Note: The `type` kwarg can be a commands.Converter subclass,
    and will attempt to convert the given values.
    """
    def inner(func):
        _func = func.callback if isinstance(func, commands.Command) else func

        if not hasattr(_func, "parser"):
            _func.parser = Parser()

        _func.parser.add_argument(*args, **kwargs)
        return func
    return inner


class ArgGroup(ArgCommand, commands.Group):
    def arg_command(self, **kwargs):
        def inner(func):
            cls = kwargs.get("cls", ArgCommand)
            kwargs["parent"] = self
            result = cls(func, **kwargs)
            self.add_command(result)
            return result
        return inner

    def arg_group(self, **kwargs):
        def inner(func):
            cls = kwargs.get("cls", ArgGroup)
            kwargs["parent"] = self
            result = cls(func, **kwargs)
            self.add_command(result)
            return result
        return inner


def command(**kwargs):
    def inner(func):
        cls = kwargs.get("cls", ArgCommand)
        return cls(func, **kwargs)
    return inner


def group(**kwargs):
    def inner(func):
        cls = kwargs.get("cls", ArgGroup)
        return cls(func, **kwargs)
    return inner

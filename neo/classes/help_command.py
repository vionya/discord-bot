# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Iterable, Optional

import discord
import neo
from discord import app_commands
from discord.ext import commands
from neo.modules import DropdownMenu, EmbedPages
from neo.tools import recursive_get_command

if TYPE_CHECKING:
    from neo import Addon
    from neo.classes.context import NeoContext


def format_command(command):
    fmt = "[{0}] {1.name}"

    if isinstance(command, commands.Group | app_commands.Group):
        symbol = "\U00002443"
    else:
        symbol = "\U00002444"

    return fmt.format(symbol, command)


AnyCommand = (
    commands.Command[Any, ..., Any]
    | app_commands.Command[Any, ..., Any]
    | app_commands.Group
)
HelpMapping = dict[Optional[commands.Cog], list[AnyCommand]]


class NeoHelpCommand(commands.HelpCommand):
    context: NeoContext

    def __init__(self):
        description = """Displays help for the bot.

        __**Command Lists**__
        In a list of commands, command types are identified symbolically:
        - A `⑄` symbol next to a listed command identifies it as a standalone command.
        - A `⑃` symbol next to a listed command identifies it as a command group.

        __**Command Help**__
        There are several elements of a command's help page to consider.

        __Description__
        Stable (completed) commands will have a description to explain
        the command's function and purpose.

        __Arguments__
        Arguments represent the relevant information that you pass to neo.
        When reading a command's arguments, the order they are listed is also
        the order in which you must provide them.

        Arguments also have some identifiers to them:
        - An argument surrounded by angle brackets (`<>`) is **required**.
        The command will not run if you do not provide this argument.
        - An argument surrounded by square brackets (`[]`) is **optional**.
        The command will run without them, or they can be provided to
        alter the result of the command.

        A unique argument type is a *flag argument*, identified by `--`

        Flag arguments are special in that they can be used
        at any spot in the arguments input, unlike non-flag (positional) arguments.
        When a command takes a flag argument, you pass it like so:
        > <command> <positional argument> **--<flag argument>**

        The input value type of a flag command may differ by command, so make sure
        to read the explanation for the argument at the bottom of the command's
        help page.
        """
        super().__init__(command_attrs={"help": description, "hidden": True})

    # Modified from discord.py source code to accomodate app commands
    async def filter_commands(
        self,
        _commands: Iterable[AnyCommand],
        /,
        *,
        sort: bool = False,
        key: Optional[Callable[[AnyCommand], Any]] = None,
    ) -> list[AnyCommand]:
        if sort and key is None:
            key = lambda c: c.name

        iterator = (
            _commands
            if self.show_hidden
            else filter(
                # App commands don't have a `hidden` attribute
                lambda c: not c.hidden if isinstance(c, commands.Command) else c,
                _commands,
            )
        )

        if self.verify_checks is False:
            # if we do not need to verify the checks then we can just
            # run it straight through normally without using await.
            return sorted(iterator, key=key) if sort else list(iterator)  # type: ignore # the key shouldn't be None

        if self.verify_checks is None and not self.context.guild:
            # if verify_checks is None and we're in a DM, don't verify
            return sorted(iterator, key=key) if sort else list(iterator)  # type: ignore

        # if we're here then we need to check every command if it can run
        async def predicate(cmd: AnyCommand) -> bool:
            if self.context.interaction:
                return True
            try:
                if isinstance(cmd, commands.Command):
                    return await cmd.can_run(self.context)
                else:
                    return True
            except commands.CommandError | app_commands.AppCommandError:
                return False

        ret = []
        for cmd in iterator:
            valid = await predicate(cmd)
            if valid:
                ret.append(cmd)

        if sort:
            ret.sort(key=key)
        return ret

    async def send_bot_help(self, mapping: HelpMapping):
        embeds = []

        for cog, _commands in mapping.items():
            # Everything is handled by `filter_commands` here, so
            # app commands will behave as normal
            if not (cog_commands := await self.filter_commands(_commands)):
                continue

            cog_name = getattr(cog, "qualified_name", "Uncategorized")
            embeds.append(
                neo.Embed(
                    title=cog_name, description=getattr(cog, "description", "")
                ).add_field(
                    name="Commands", value="\n".join(map(format_command, cog_commands))
                )
            )

        pages = EmbedPages(embeds)
        menu = DropdownMenu.from_pages(
            pages, embed_auto_label=True, embed_auto_desc=True
        )
        await menu.start(self.context)

    async def send_cog_help(self, cog: Addon):
        cog_name = cog.qualified_name
        cog_commands = await self.filter_commands(cog.get_commands())

        embed = neo.Embed(
            title=cog_name, description=getattr(cog, "description", "No description")
        ).add_field(name="Commands", value="\n".join(map(format_command, cog_commands)))

        await self.context.send(embed=embed)

    async def send_command_help(self, command: AnyCommand):
        if isinstance(command, app_commands.Command | app_commands.Group):
            # If this is an app command, provide no specific signature
            # TODO: Generate signatures?
            embed = neo.Embed(
                title=f"/{command.qualified_name}",
                description="{}\n".format(command.description or "No description"),
            )
        else:
            # If this is a text command, provide its actual signature
            embed = neo.Embed(
                title=f"{self.context.clean_prefix}{command.qualified_name} {command.signature}",
                description="{}\n".format(command.help or "No description"),
            )

        if isinstance(command, commands.Command) and command.aliases:
            # If this is a text command, handle its aliases
            aliases = ", ".join(
                f"**{alias}**" for alias in [command.name, *command.aliases]
            )
            embed.add_field(name="Command Aliases", value=aliases, inline=False)

        if hasattr(command, "get_args_help"):
            # If this is an args command, generate the helps message from the args
            args_help = ""
            for dest, help in command.get_args_help():  # type: ignore
                args_help += f"\n\n**{dest}** {help}"
            embed.add_field(name="Flag Arguments", value=args_help, inline=False)

        if isinstance(command, commands.Group | app_commands.Group):

            # Generate the ancestral path (the qualified name up to
            # the second to last index)
            def get_ancestral_path(command: AnyCommand) -> str:
                path = command.qualified_name.split(" ")
                return " ".join(path[:-1])

            embed.add_field(
                name="Subcommands",
                value="\n".join(
                    map(
                        lambda sub: f"{get_ancestral_path(sub)} **{sub.name}**",
                        command.walk_commands(),
                    )
                )
                or "No subcommands",
                inline=False,
            )

        if getattr(command, "with_app_command", False) is True:
            # If this is a hybrid command, indicate that it CAN be used as a slash command
            embed.set_footer(text="This command can be used as a slash command")

        if isinstance(command, app_commands.Command):
            # If this is an app command, indicate that it MUST be used as a slash command
            embed.set_footer(text="This command must be used as a slash command")

        await self.context.send(embed=embed)

    async def send_group_help(self, group: commands.Group | app_commands.Group):
        # Group help is re-routed directly to command help, which unifies
        # functionality
        await self.send_command_help(group)

    def get_destination(self) -> NeoContext:
        # Set the destination to ctx to allow ephemeral tricks to work
        return self.context

    async def command_callback(
        self, ctx: NeoContext, /, *, command: Optional[str] = None
    ) -> None:
        # If no command has been provided or the command exists as a text command,
        # invoke the standard help command callback
        # (text commands are given priority)
        if command is None or ctx.bot.get_command(command):
            return await super().command_callback(ctx, command=command)

        # If this command exists in the app command tree, handle it accordingly
        elif command in [
            cmd.qualified_name
            for cmd in ctx.bot.tree.walk_commands(
                type=discord.AppCommandType.chat_input
            )
        ]:
            # Recursively fetch the command based on its name
            # If it's a qualified name, it tries to traverse until it fails
            cmd = recursive_get_command(ctx.bot.tree, command)

            if cmd is None:
                string = await discord.utils.maybe_coroutine(
                    self.command_not_found, self.remove_mentions(command.split(" ")[0])
                )
                return await self.send_error_message(string)

            if isinstance(
                cmd, app_commands.Group
            ):  # Should this just always just defer to `send_command_help`?`
                return await self.send_group_help(cmd)
            else:
                return await self.send_command_help(cmd)

        else:
            msg = await discord.utils.maybe_coroutine(self.command_not_found, command)
            return await self.send_error_message(msg)

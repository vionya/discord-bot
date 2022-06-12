# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

from operator import attrgetter
from typing import TYPE_CHECKING, Any, Callable, Iterable, Optional

import discord
import neo
from discord import app_commands
from discord.ext import commands
from neo.classes.app_commands import AutoEphemeralAppCommand
from neo.modules import DropdownMenu, EmbedPages
from neo.tools import recursive_get_command
from neo.tools.decorators import with_docstring
from neo.types.commands import AnyCommand

if TYPE_CHECKING:
    from neo import Addon, Neo
    from neo.classes.context import NeoContext
    from typing_extensions import Self

    HelpMapping = dict[Optional[Addon], list[AnyCommand]]
else:
    HelpMapping = dict[Optional[Any], list[AnyCommand]]

# Generate the ancestral path (the qualified name up to
# the second to last index)
def get_ancestral_path(command: AnyCommand) -> str:
    path = command.qualified_name.split(" ")
    return " ".join(path[:-1])


def format_command(command: AnyCommand):
    fmt = "[{0}] {1} **{2.name}**" if command.parent is not None else "[{0}] {2.name}"

    if isinstance(command, commands.Group | app_commands.Group):
        symbol = "\U00002443"
    else:
        symbol = "\U00002444"

    return fmt.format(symbol, get_ancestral_path(command), command)


class AppHelpCommand(AutoEphemeralAppCommand):
    """Displays help for the bot.

    __**Command Lists**__
    In a list of commands, command types are identified symbolically:
    - A `⑄` symbol next to a listed command identifies it as a standalone command.
    - A `⑃` symbol next to a listed command identifies it as a command group.

    __**Using Slash Commands**__
    neo phoenix uses a custom system for slash commands which lets you customize
    your experience. Each command automatically includes a special "`ephemeral`"
    option. This option controls whether the response to your command will be sent
    as an *ephemeral message*.

    *Ephemeral messages* are unique because you are the **only** person who can
    see them - nobody else will even know you ran a command. You can take
    advantage of the `ephemeral` option to decide whether or not you want other
    people to see what you're doing.

    With a configured profile, you can even change whether responses are ephemeral
    by default! By changing the `default_ephemeral` option, you can choose to
    have responses be public or private without you having to do anything.

    Of course, the `ephemeral` parameter will override the default setting if you
    ever want to do something different.
    """

    def __init__(self, bot: Neo):
        self.bot = bot

        # Copy the __doc__ from the class to the actual callback
        self.actual_callback.__func__.__doc__ = self.__class__.__doc__
        super().__init__(
            name="help",
            description=(self.__class__.__doc__ or "").splitlines()[0],
            callback=self.actual_callback,  # type: ignore
        )
        self.binding = self
        self.autocomplete("command")(self.actual_autocomplete)

    @app_commands.describe(command="The command to get help for")
    async def actual_callback(
        self, interaction: discord.Interaction, command: Optional[str] = None
    ):
        if command is None:
            return await self.send_bot_help(interaction, self.get_mapping())

        cmd = recursive_get_command(self.bot.tree, command)
        if not cmd:
            raise NameError(f"Command `{command}` does not exist")

        else:
            return await self.send_command_help(interaction, cmd)

    async def actual_autocomplete(self, interaction: discord.Interaction, current: str):
        all_commands = set(
            [
                *map(attrgetter("qualified_name"), self.bot.walk_commands()),
                *map(attrgetter("qualified_name"), self.bot.tree.walk_commands()),
            ]
        )
        return [
            *map(
                lambda k: app_commands.Choice(name=k, value=k),
                filter(lambda k: current in k, all_commands),
            )
        ][:25]

    def get_mapping(self) -> HelpMapping:
        mapping = {}
        mapping.update(
            {addon: addon.get_commands() for addon in self.bot.cogs.values()}
        )
        mapping.update(
            {
                None: [
                    command
                    for command in self.bot.tree.get_commands(
                        type=discord.AppCommandType.chat_input
                    )
                    if getattr(command, "addon", None) is None
                ]
            }
        )
        return mapping

    def filter_commands(self, _commands: Iterable[AnyCommand]):
        if isinstance(_commands, app_commands.Group):
            return _commands.commands

        return list(
            filter(
                lambda cmd: isinstance(cmd, app_commands.Command | app_commands.Group),
                _commands,
            )
        )

    async def send_bot_help(
        self, interaction: discord.Interaction, mapping: HelpMapping
    ):
        embeds = []

        for cog, _commands in mapping.items():
            # Everything is handled by `filter_commands` here, so
            # app commands will behave as normal
            if not (cog_commands := self.filter_commands(_commands)):
                continue

            cog_name = getattr(cog, "qualified_name", "Uncategorized")
            embeds.append(
                neo.Embed(title=cog_name, description=getattr(cog, "description", ""))
                .add_field(
                    name="Commands",
                    value="\n".join(map(format_command, cog_commands)),
                    inline=False,
                )
                .add_field(
                    name="Lost?",
                    value="Try /help `command: help` to learn more about neo phoenix",
                    inline=False,
                )
            )

        pages = EmbedPages(embeds)
        menu = DropdownMenu.from_pages(
            pages, embed_auto_label=True, embed_auto_desc=True
        )
        await menu.start(interaction)

    async def send_command_help(
        self, interaction: discord.Interaction, command: AnyCommand
    ):
        description = (
            max(
                command.description,
                getattr(command.callback, "__doc__", "") or ""  # type: ignore
                if hasattr(command, "callback")
                else "",
                key=len,
            )
            or "No description"
        )

        # TODO: Generate signatures?
        embed = neo.Embed(
            title=f"/{command.qualified_name}",
            description="{}\n".format(description),
        )

        if isinstance(command, app_commands.Group):

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

        if hasattr(command, "callback") and (deprecation := getattr(command.callback, "_deprecated", None)):  # type: ignore
            embed.description = (
                "**==DEPRECATION NOTICE==**\nThis command is deprecated and "
                "will be removed in the future.{0}\n\n{1}".format(
                    f"\nExtra Info: {deprecation}"
                    if isinstance(deprecation, str)
                    else "",
                    embed.description,
                )
            )

        await interaction.response.send_message(embed=embed)


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
            try:
                if self.context.interaction:
                    if isinstance(cmd, commands.HybridCommand | commands.HybridCommand):
                        return True

                if not isinstance(cmd, app_commands.Command | app_commands.Group):
                    return await cmd.can_run(self.context)
                else:
                    return True
            except Exception:
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
        await menu.start(self.get_destination())

    async def send_cog_help(self, cog: Addon):
        cog_name = cog.qualified_name
        cog_commands = await self.filter_commands(cog.get_commands())

        embed = neo.Embed(
            title=cog_name, description=getattr(cog, "description", "No description")
        ).add_field(name="Commands", value="\n".join(map(format_command, cog_commands)))

        await self.get_destination().send(embed=embed)

    async def send_command_help(self, command: AnyCommand):
        if isinstance(command, app_commands.Command | app_commands.Group):
            # If this is an app command, provide no specific signature
            description = (
                max(
                    command.description,
                    getattr(command.callback, "__doc__", "") or ""  # type: ignore
                    if hasattr(command, "callback")
                    else "",
                    key=len,
                )
                or "No description"
            )

            # TODO: Generate signatures?
            embed = neo.Embed(
                title=f"/{command.qualified_name}",
                description="{}\n".format(description),
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

        if hasattr(command, "callback") and (deprecation := getattr(command.callback, "_deprecated", None)):  # type: ignore
            embed.description = (
                "**==DEPRECATION NOTICE==**\nThis command is deprecated and "
                "will be removed in the future.{0}\n\n{1}".format(
                    f"\nExtra Info: {deprecation}"
                    if isinstance(deprecation, str)
                    else "",
                    embed.description,
                )
            )

        await self.get_destination().send(embed=embed)

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
        # If no command has been provided,
        # invoke the standard help command callback
        if command is None:
            return await super().command_callback(ctx)

        cmd: Optional[AnyCommand] = None
        # If help is called as a slash command, prioritize slash commands
        # This lets overloaded command names be accessed
        if ctx.interaction:
            cmd = recursive_get_command(ctx.bot.tree, command) or ctx.bot.get_command(
                command
            )
        # Otherwise, prioritize text commands before slash commands
        else:
            cmd = ctx.bot.get_command(command) or recursive_get_command(
                ctx.bot.tree, command
            )

        # If cmd is none, the command does not exist
        # Error accordingly
        if cmd is None:
            string = await discord.utils.maybe_coroutine(
                self.command_not_found, self.remove_mentions(command)
            )
            return await self.send_error_message(string)

        return await self.send_command_help(cmd)

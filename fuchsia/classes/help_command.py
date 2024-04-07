# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 sardonicism-04
from __future__ import annotations

import re
from operator import attrgetter
from typing import TYPE_CHECKING, Any, Optional
from itertools import chain

import discord
from discord import app_commands

import fuchsia
from fuchsia.classes.app_commands import AutoEphemeralAppCommand
from fuchsia.modules import DropdownMenu, EmbedPages
from fuchsia.tools import recursive_get_command
from fuchsia.types.commands import AnyCommand

if TYPE_CHECKING:
    from collections.abc import Iterable

    from fuchsia import Addon, Fuchsia

    HelpMapping = dict[Optional[Addon], list[AnyCommand]]
else:
    HelpMapping = dict[Optional[Any], list[AnyCommand]]

PARAM_TYPE_MAPPING = {
    discord.AppCommandOptionType.string: "Text",
    discord.AppCommandOptionType.integer: "An integer",
    discord.AppCommandOptionType.boolean: "A boolean (yes/no)",
    discord.AppCommandOptionType.user: "A Discord user",
    discord.AppCommandOptionType.channel: "A server channel",
    discord.AppCommandOptionType.role: "A server role",
    discord.AppCommandOptionType.mentionable: "A ping-able target",
    discord.AppCommandOptionType.number: "A number",
    discord.AppCommandOptionType.attachment: "A file",
}
LEADING_WHITESPACE = re.compile(r"(?!$)^\s+", re.MULTILINE)


# Generate the ancestral path (the qualified name up to
# the second to last index)
def get_ancestral_path(command: AnyCommand) -> str:
    path = command.qualified_name.split(" ")
    return " ".join(path[:-1])


def format_command(command: AnyCommand):
    fmt = (
        "[`{0}`] {1} **{2.name}**"
        if getattr(command, "parent", None)
        else "[`{0}`] {2.name}"
    )

    match command:
        case app_commands.Group():
            symbol = "\U00002443"
        case app_commands.ContextMenu():
            symbol = "\U00002261"
        case _:
            symbol = "\U00002444"

    return fmt.format(symbol, get_ancestral_path(command), command)


def generate_signature(command: AnyCommand) -> str:
    """Generates a signature for a command.

    A signature consists of the command's qualified name, and its available
    parameters. Required parameters are surrounded in angle (<>) brackets, and
    optional parameters in square ([]) brackets.

    :param command: The command to generate a signature for
    :type command: ``AnyCommand``

    :return: A signature for the command
    :rtype: ``str``
    """
    signature = []
    match command:
        case app_commands.Group():
            signature.append(f"/{command.qualified_name} [*subcommand*]")
        case app_commands.Command():
            signature.append(f"/{command.qualified_name}")
            for param in command.parameters:
                if param.required:
                    signature.append(f"<{param.display_name}>")
                else:
                    signature.append(f"[{param.display_name}]")
        case _:
            signature.append(command.qualified_name)
    return " ".join(signature)


def generate_param_help(command: app_commands.Command) -> str:
    """Generates a string with help for all parameters for a command.

    A help string consists of the parameter's name, whether it's required,
    its required input type, default value (if applicable), and input value
    range (if applicable).

    :param command: The command to generate a help string for
    :type command: ``discord.app_commands.Command``

    :return: A help string for the command's parameters
    :rtype: ``str``
    """
    descriptions = []
    for param in command.parameters:
        desc = f"`{param.display_name}`: {param.description}"

        if param.required:
            desc += "\n↳ This is a required parameter"
        desc += f"\n↳ **Input Type**: {PARAM_TYPE_MAPPING.get(param.type, param.type.value)}"
        if param.default:
            desc += f"\n↳ **Default**: `{param.default}`"

        mi, ma = param.min_value, param.max_value
        if mi is not None and ma is not None:
            desc += f"\n↳ **Value Range**: `{mi}..{ma}`"
        elif mi is not None:
            desc += f"\n↳ **Min Value**: `{mi}`"
        elif ma is not None:
            desc += f"\n↳ **Max Value**: `{ma}`"
        descriptions.append(desc)
    return "\n\n".join(descriptions)


class AppHelpCommand(AutoEphemeralAppCommand):
    """Displays help for the bot.

    ## Command Lists
    In a list of commands, command types are identified symbolically:
    - A `⑄` symbol next to a listed command identifies it as a standalone[JOIN]
    command
    - A `⑃` symbol next to a listed command identifies it as a command group
    - A `≡` symbol next to a listed command identifies it as a context[JOIN]
    menu command

    ## Using Slash Commands
    fuchsia uses a custom system for slash commands which lets you[JOIN]
    customize your experience. Each command automatically includes a[JOIN]
    special "`private`" option. This option controls whether the response[JOIN]
    to your command will be sent as an *ephemeral message*.

    *Ephemeral messages* are unique because you are the **only** person[JOIN]
    who can see them - nobody else will even know you ran a command. You[JOIN]
    can take advantage of the `private` option to decide whether or not[JOIN]
    you want other people to see what you're doing.

    With a configured profile, you can even change whether responses are[JOIN]
    ephemeral by default! By changing the `Private By Default` option, you[JOIN]
    can choose to have responses be public or private without you having[JOIN]
    to do anything.

    Of course, the `private` parameter will override the default setting[JOIN]
    if you ever want to do something different.
    """

    def __init__(self, bot: Fuchsia):
        self.bot = bot

        # Copy the __doc__ from the class to the actual callback
        self._callback_impl.__func__.__doc__ = self.__class__.__doc__
        super().__init__(
            name="help",
            description=(self.__class__.__doc__ or "").splitlines()[0],
            callback=self._callback_impl,  # type: ignore
        )
        self.binding = self
        self.autocomplete("command")(self._autocomplete_impl)

    @app_commands.describe(command="The command to get help for")
    async def _callback_impl(
        self, interaction: discord.Interaction, command: Optional[str] = None
    ):
        if command is None:
            return await self.send_bot_help(interaction, self.get_mapping())

        cmd = (
            self.bot.tree.get_command(command, type=discord.AppCommandType.user)
            or self.bot.tree.get_command(
                command, type=discord.AppCommandType.message
            )
            or recursive_get_command(self.bot.tree, command)
        )
        if not cmd:
            raise NameError(f"Command `{command}` does not exist")
        else:
            return await self.send_command_help(interaction, cmd)

    async def _autocomplete_impl(
        self, interaction: discord.Interaction, current: str
    ):
        all_commands = chain(
            self.bot.tree.walk_commands(),
            self.bot.tree.get_commands(type=discord.AppCommandType.user),
            self.bot.tree.get_commands(type=discord.AppCommandType.message),
        )

        return [
            app_commands.Choice(
                name=("" if isinstance(k, app_commands.ContextMenu) else "/")
                + k.qualified_name,
                value=k.qualified_name,
            )
            for k in all_commands
            if current.casefold().removeprefix("/")
            in k.qualified_name.casefold()
        ][:25]

    def get_mapping(self) -> HelpMapping:
        mapping: HelpMapping = {
            addon: addon.get_commands() for addon in self.bot.cogs.values()
        }
        mapping[None] = [
            command
            for command in self.bot.tree.get_commands(type=None)
            if getattr(command, "addon", None) is None
        ]
        return mapping

    def filter_commands(self, commands: Iterable[AnyCommand]):
        if isinstance(commands, app_commands.Group):
            return commands.commands

        return list(
            filter(
                lambda cmd: isinstance(
                    cmd,
                    (
                        app_commands.Command,
                        app_commands.Group,
                        app_commands.ContextMenu,
                    ),
                ),
                commands,
            )
        )

    async def send_bot_help(
        self, interaction: discord.Interaction, mapping: HelpMapping
    ):
        embeds = []

        for cog, commands in mapping.items():
            # Everything is handled by `filter_commands` here, so
            # app commands will behave as normal
            if not (cog_commands := self.filter_commands(commands)):
                continue

            cog_name = getattr(cog, "qualified_name", "Uncategorized")
            embeds.append(
                fuchsia.Embed(
                    title=cog_name, description=getattr(cog, "description", "")
                )
                .add_field(
                    name="Commands",
                    value="\n".join(map(format_command, cog_commands)),
                    inline=False,
                )
                .add_field(
                    name="Lost?",
                    value="Try /help `command: help` to learn more about fuchsia",
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
        description = LEADING_WHITESPACE.sub(
            "",
            max(
                getattr(command, "description", ""),
                (
                    getattr(command.callback, "__doc__", "") or ""  # type: ignore
                    if hasattr(command, "callback")
                    else ""
                ),
                key=len,
            )
            or "No description",
        ).replace(
            "[JOIN]\n", " "
        )  # join multiline strings

        signature = generate_signature(command)
        embed = fuchsia.Embed(
            title=signature,
            description=description,
        )

        if isinstance(command, app_commands.Command):
            embed.add_field(
                name="Parameters",
                value=generate_param_help(command),
                inline=False,
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

        if hasattr(command, "callback") and (
            deprecation := getattr(command.callback, "_deprecated", None)  # type: ignore
        ):
            embed.description = (
                "**==DEPRECATION NOTICE==**\nThis command is deprecated and "
                "will be removed in the future.{0}\n\n{1}".format(
                    (
                        f"\nExtra Info: {deprecation}"
                        if isinstance(deprecation, str)
                        else ""
                    ),
                    embed.description,
                )
            )

        await interaction.response.send_message(embed=embed)

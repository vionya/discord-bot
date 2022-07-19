# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

import re
from operator import attrgetter
from typing import TYPE_CHECKING, Any, Optional

import discord
from discord import app_commands

import neo
from neo.classes.app_commands import AutoEphemeralAppCommand
from neo.modules import DropdownMenu, EmbedPages
from neo.tools import recursive_get_command
from neo.types.commands import AnyCommand

if TYPE_CHECKING:
    from collections.abc import Iterable

    from neo import Addon, Neo

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

    if isinstance(command, app_commands.Group):
        symbol = "\U00002443"
    else:
        symbol = "\U00002444"

    return fmt.format(symbol, get_ancestral_path(command), command)


leading_whitespace = re.compile(r"(?!$)^\s+", re.MULTILINE)


class AppHelpCommand(AutoEphemeralAppCommand):
    """Displays help for the bot.

    __**Command Lists**__
    In a list of commands, command types are identified symbolically:
    - A `⑄` symbol next to a listed command identifies it as a standalone command.
    - A `⑃` symbol next to a listed command identifies it as a command group.

    __**Using Slash Commands**__
    neo phoenix uses a custom system for slash commands which lets you customize
    your experience. Each command automatically includes a special "`private`"
    option. This option controls whether the response to your command will be sent
    as an *ephemeral message*.

    *Ephemeral messages* are unique because you are the **only** person who can
    see them - nobody else will even know you ran a command. You can take
    advantage of the `private` option to decide whether or not you want other
    people to see what you're doing.

    With a configured profile, you can even change whether responses are ephemeral
    by default! By changing the `Private By Default` option, you can choose to
    have responses be public or private without you having to do anything.

    Of course, the `private` parameter will override the default setting if you
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
        all_commands = map(attrgetter("qualified_name"), self.bot.tree.walk_commands())
        return [
            app_commands.Choice(name=k, value=k) for k in all_commands if current in k
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
        description = leading_whitespace.sub(
            "",
            max(
                command.description,
                getattr(command.callback, "__doc__", "") or ""  # type: ignore
                if hasattr(command, "callback")
                else "",
                key=len,
            )
            or "No description",
        )

        # TODO: Generate signatures?
        embed = neo.Embed(
            title=f"/{command.qualified_name}",
            description=description,
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

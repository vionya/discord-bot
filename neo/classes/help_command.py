# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from typing import Optional

import discord
import neo
from discord.ext import commands
from neo.classes.context import NeoContext
from neo.modules import DropdownMenu, EmbedPages


def format_command(command):
    fmt = "[{0}] {1.name}"

    if isinstance(command, commands.Group):
        symbol = "\U00002443"
    else:
        symbol = "\U00002444"

    return fmt.format(symbol, command)


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
        super().__init__(command_attrs={"help": description})

    async def send_bot_help(self, mapping):
        embeds = []

        for cog, _commands in mapping.items():
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

    async def send_cog_help(self, cog):
        cog_name = cog.qualified_name
        cog_commands = await self.filter_commands(cog.get_commands())

        embed = neo.Embed(
            title=cog_name, description=getattr(cog, "description", "No description")
        ).add_field(name="Commands", value="\n".join(map(format_command, cog_commands)))

        await self.context.send(embed=embed)

    async def send_command_help(
        self, command: commands.Command | discord.app_commands.Command
    ):
        if isinstance(command, discord.app_commands.Command):
            embed = neo.Embed(
                title=f"/{command.qualified_name}",
                description="{}\n".format(command.description or "No description"),
            )
        else:
            embed = neo.Embed(
                title=f"{self.context.clean_prefix}{command.qualified_name} {command.signature}",
                description="{}\n".format(command.help or "No description"),
            )

        if isinstance(command, commands.Command) and command.aliases:
            aliases = ", ".join(
                f"**{alias}**" for alias in [command.name, *command.aliases]
            )
            embed.add_field(name="Command Aliases", value=aliases, inline=False)

        if hasattr(command, "get_args_help"):
            args_help = ""
            for dest, help in command.get_args_help():  # type: ignore
                args_help += f"\n\n**{dest}** {help}"
            embed.add_field(name="Flag Arguments", value=args_help, inline=False)

        if isinstance(command, commands.Group):
            embed.add_field(
                name="Subcommands",
                value="\n".join(
                    map(
                        lambda sub: f"{sub.full_parent_name} **{sub.name}**",
                        command.walk_commands(),
                    )
                )
                or "No subcommands",
                inline=False,
            )

        if getattr(command, "with_app_command", False) is True:
            embed.set_footer(text="This command can be used as a slash command")

        if isinstance(command, discord.app_commands.Command):
            embed.set_footer(text="This command must be used as a slash command")

        await self.context.send(embed=embed)

    async def send_group_help(self, group):
        await self.send_command_help(group)

    def get_destination(self) -> NeoContext:
        return self.context

    async def command_callback(
        self, ctx: NeoContext, /, *, command: Optional[str] = None
    ) -> None:
        if command is None or command in ctx.bot.all_commands:
            return await super().command_callback(ctx, command=command)

        elif command in [
            cmd.qualified_name
            for cmd in ctx.bot.tree.walk_commands(
                type=discord.AppCommandType.chat_input
            )
        ]:
            cmd = ctx.bot.tree.get_command(
                command, type=discord.AppCommandType.chat_input
            )

            if cmd is None:
                string = await discord.utils.maybe_coroutine(
                    self.command_not_found, self.remove_mentions(command.split(" ")[0])
                )
                return await self.send_error_message(string)

            if isinstance(cmd, discord.app_commands.Group):
                return await self.send_group_help(cmd)
            else:
                return await self.send_command_help(cmd)

        else:
            msg = await discord.utils.maybe_coroutine(self.command_not_found, command)
            return await self.send_error_message(msg)

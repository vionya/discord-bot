# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Optional

import discord
from discord.ext import commands

import fuchsia
from fuchsia.classes.transformers import codeblock_transformer
from fuchsia.modules import ButtonsMenu, Pages
from fuchsia.modules.exec import ExecWrapper
from fuchsia.tools.formatters import Table, format_exception

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fuchsia.classes.context import FuchsiaContext


class Devel(fuchsia.Addon):
    """Developer-only utility commands"""

    def __init__(self, bot: fuchsia.Fuchsia):
        self.bot = bot
        self._exec_scope: dict[str, Any] = {}
        self._last_exec_result: Any = None

    async def cog_check(self, ctx):
        if not await self.bot.is_owner(ctx.author):
            raise commands.NotOwner("You do not own this bot.")
        return True

    def env_from_context(self, ctx: FuchsiaContext):
        return {
            "ctx": ctx,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
            "channel": ctx.channel,
            "bot": ctx.bot,
            "_": self._last_exec_result,
        }

    @commands.guild_only()
    @commands.command(name="cleanup", aliases=["clean"])
    async def dev_cleanup(self, ctx: FuchsiaContext, amount: int = 5):
        """Cleanup the bot's messages from a channel"""
        assert isinstance(ctx.me, discord.Member) and isinstance(
            ctx.channel, discord.TextChannel | discord.VoiceChannel
        )

        can_manage = ctx.channel.permissions_for(ctx.me).manage_messages

        def check(message: discord.Message) -> bool:
            if can_manage:
                return any(
                    [
                        message.author == ctx.me,
                        (ctx.prefix and message.content.startswith(ctx.prefix)),
                    ]
                )
            return message.author == ctx.me

        purged = await ctx.channel.purge(
            limit=amount, bulk=can_manage, check=check
        )
        await ctx.send(f"Cleaned {len(purged)} message(s).", delete_after=5)

    @commands.command(name="exec", aliases=["e"])
    async def dev_exec(
        self,
        ctx: FuchsiaContext,
        *,
        code: str = commands.parameter(
            converter=codeblock_transformer().wrapped
        ),
    ):
        """Executes some code, retaining the result"""
        (globals_ := self.env_from_context(ctx)).update(
            **(self._exec_scope | globals())
        )
        pages = Pages(
            "\r",
            1500,
            joiner="",
            prefix="```py\n",
            suffix="\n```",
            use_embed=True,
        )
        menu = ButtonsMenu(pages)

        try:
            async for res in ExecWrapper(code, globals_, self._exec_scope):
                if res is None:
                    continue

                self._last_exec_result = res
                res = repr(res) if not isinstance(res, str) else res
                menu.pages.append("\n{}".format(res))

                if not menu.running:
                    await menu.start(ctx, as_reply=True)
            await ctx.message.add_reaction("\U00002611")

        except (
            BaseException
        ) as e:  # Ensure that all errors in exec are handled here
            menu.pages.append(
                "\n{}".format(format_exception(e, no_filename=True))
            )
            await menu.start(ctx)

    @commands.command(name="sql")
    async def dev_sql(
        self,
        ctx: FuchsiaContext,
        *,
        query: str = commands.parameter(
            converter=codeblock_transformer().wrapped
        ),
    ):
        """Perform an SQL query"""
        data = await self.bot.db.fetch(query)
        if len(data) == 0:
            return await ctx.send("Query executed successfully")

        table = Table()
        table.init_columns(*data[0].keys())  # Infer headers from column names
        for row in data:
            table.add_row(*map(str, row.values()))

        pages = Pages(
            table.display(), 1500, joiner="", prefix="```py\n", suffix="\n```"
        )
        menu = ButtonsMenu(pages)
        await menu.start(ctx)

    @commands.command(name="addon")
    async def dev_addon(
        self,
        ctx: FuchsiaContext,
        action: Optional[Literal["reload", "load", "unload"]] = "reload",
        *addons: str,
    ):
        """
        Manage addons

        It's not a great idea to unload everything
        """
        action_method: Callable[[str], Awaitable[None]] = getattr(
            self.bot, f"{action}_extension"
        )
        failed: list[str] = []
        if "~" in addons:
            addons = (*self.bot.extensions.keys(),)
        for addon in addons:
            try:
                await action_method(addon)
            except BaseException as e:
                failed.append("```py\n" + format_exception(e) + "\n```")

        if failed:
            menu = ButtonsMenu.from_iterable(failed, use_embed=True)
            await menu.start(ctx)
            return
        await ctx.send_confirmation()

    @commands.guild_only()
    @commands.command(name="sync")
    async def dev_sync(
        self,
        ctx: FuchsiaContext,
        clear_commands: bool = False,
        glob: bool = False,
    ):
        """
        Sync all app commands to the current guild or global namespace
        """
        assert ctx.guild

        if clear_commands:
            self.bot.tree.clear_commands(guild=None if glob else ctx.guild)
        else:
            self.bot.tree.copy_global_to(guild=ctx.guild)
        await self.bot.tree.sync(guild=None if glob else ctx.guild)
        await ctx.send_confirmation()


async def setup(bot):
    await bot.add_cog(Devel(bot))

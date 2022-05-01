# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

import asyncio
import random
import shlex
from collections import Counter
from functools import partial
from sys import version as py_version
from types import SimpleNamespace
from typing import TYPE_CHECKING

import discord
import neo
from discord.ext import commands
from googletrans import LANGUAGES, Translator
from neo.classes.converters import mention_converter
from neo.classes.formatters import Table
from neo.modules import DropdownMenu, EmbedPages, args, cse, dictionary
from neo.tools import shorten

from .auxiliary.utility import (
    LANGUAGE_CODES,
    InfoButtons,
    SwappableEmbedButton,
    definitions_to_embed,
    get_translation_kwargs,
    result_to_embed,
    translate
)

if TYPE_CHECKING:
    from neo.classes.context import NeoContext

BADGE_MAPPING = {
    "staff": "<:_:863197443386900541>",
    "discord_certified_moderator": "<:_:863197442996305960>",
    "partner": "<:_:863197443311403008>",
    "hypesquad": "<:_:863197443281911808>",
    "hypesquad_balance": "<:_:863197443244294164>",
    "hypesquad_bravery": "<:_:863197443238920242>",
    "hypesquad_brilliance": "<:_:863197443268673567>",
    "bug_hunter": "<:_:863197442983067678>",
    "bug_hunter_level_2": "<:_:863197443083730955>",
    "early_verified_bot_developer": "<:_:863197443083730958>",
    "early_supporter": "<:_:863197442840068117>",
}
ICON_MAPPING = {
    "guild_owner": "<:_:863197442996305941>",
    "bot_tag": "<:_:863197442937061416>",
    "verified_bot_tag": "<:_:863197443083730959><:_:863197443565813780>"
}
PREMIUM_ICON_MAPPING = {
    0: "",
    1: "<:_:868138562690875452>",
    2: "<:_:868138562737041458>",
    3: "<:_:868138562913173564>"
}
ASSOCIATION_FILTER = [
    ("Server Default Role", discord.Role.is_default),
    ("Managed by Bot", discord.Role.is_bot_managed),
    ("Booster-Exclusive Role", discord.Role.is_premium_subscriber),
    ("Managed by Integration", discord.Role.is_integration)
]


def get_browser_links(avatar: discord.Asset):
    formats = ["PNG", "JPG", "WEBP"]
    if avatar.is_animated():
        formats.append("GIF")

    return " • " .join(
        f"[{fmt}]({avatar.with_format(fmt.lower())})" for fmt in formats)


class Utility(neo.Addon):
    """Various utility commands"""

    def __init__(self, bot: neo.Neo):
        self.bot = bot
        with open(bot.cfg["privacy_policy_path"]) as policy:
            header, body = policy.read().split("\n", 1)
            header = header.lstrip("# ")
            body = body.replace("  \n", "\n")  # Ensure proper formatting on mobile
        self.privacy_embed = neo.Embed(title=header, description=body)
        self.translator = Translator(raise_exception=True)
        asyncio.create_task(self.__ainit__())

    async def __ainit__(self):
        await self.bot.wait_until_ready()

        # These both take a ClientSession, so we wait until ready so we can use the bot's
        self.google = cse.Search(
            key=self.bot.cfg["bot"]["cse_keys"],
            engine_id=self.bot.cfg["bot"]["cse_engine"],
            session=self.bot.session
        )
        self.dictionary = dictionary.Define(self.bot.session)
        self.appinfo = await self.bot.application_info()
        buttons = [
            discord.ui.Button(
                url=self.bot.cfg["support"]["url"],
                label="Support Server",
                disabled=self.bot.cfg["support"]["disabled"],
            ),
            discord.ui.Button(
                url=self.bot.cfg["upstream_url"],
                label="Source Code",
                row=1
            )
        ]
        self.info_buttons = partial(
            InfoButtons,
            self.privacy_embed,
            False,  # not self.appinfo.bot_public,
            buttons=buttons,
            presets=self.bot.cfg["invite_presets"],
            application_id=self.bot.user.id
        )
        self.bot.add_view(self.info_buttons())

    @commands.hybrid_command(name="google", aliases=["g"])
    @discord.app_commands.describe(query="The query to search for")
    async def google_command(self, ctx, *, query: str):
        """Search Google for a query"""
        await self.google_command_callback(ctx, query)

    @commands.hybrid_command(name="image", aliases=["i"])
    @discord.app_commands.describe(query="The query to search for")
    async def google_image_command(self, ctx, *, query: str):
        """Search Google Images for a query"""
        await self.google_command_callback(ctx, query, True)

    async def google_command_callback(self, ctx, query: str, image: bool = False):
        resp = await self.google.search(query, image=image)

        embeds = [*map(result_to_embed, resp)]
        if not embeds:
            raise RuntimeError("Search returned no results")

        pages = EmbedPages(embeds)
        menu = DropdownMenu.from_pages(
            pages, embed_auto_label=True, embed_auto_desc=True)
        await menu.start(ctx)

    @args.add_arg(
        "word",
        nargs="+",
        help="The word to search a dictionary for"
    )
    @args.add_arg(
        "-lc", "--lang_code",
        default="en_US",
        help="The language code of the dictionary to search\n```\n" + LANGUAGE_CODES + "\n```"
    )
    @args.command(name="define")
    async def dictionary_command(self, ctx, *, query):
        """Search the dictionary for a word's definition"""
        try:
            resp = await self.dictionary.define(
                " ".join(query.word),
                lang_code=query.lang_code
            )
        except dictionary.DefinitionError:
            raise RuntimeError("No definition found")

        embeds = []
        for word in resp.words:
            embeds.extend(definitions_to_embed(word))
        if not embeds:
            raise RuntimeError("No definition found")

        pages = EmbedPages(embeds)
        menu = DropdownMenu.from_pages(
            pages, embed_auto_label=True, embed_auto_desc=True)
        await menu.start(ctx)

    @commands.command(
        name="translate",
        aliases=["tr"],
        usage="[directive] <content>"
    )
    async def translation_command(self, ctx, *, input):
        """
        Translate a string of text

        If just a string of text is supplied, the source language will be
        auto-detected and translated to English.
        Ex: `translate amigo`

        To translate between particular languages, use the `->` operator.
        Ex: `translate en->ja Hello` *Translates "hello" to Japanese*
        Ex: `translate *->ja Hello` *Same as above, but auto-detects source language*
        """
        content, kwargs = get_translation_kwargs(input)
        translated = await translate(self.translator, content, **kwargs)
        embed = neo.Embed(
            description=f"**Source Language** `{kwargs['src']}` "
            f"[{LANGUAGES.get(translated.src, 'Auto-Detected').title()}]"
            f"\n**Destination Language** {LANGUAGES.get(translated.dest, 'Unknown').title()}"
        ).add_field(
            name="Translated Content",
            value=shorten(translated.text, 1024),
            inline=False
        )
        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.bot_has_permissions(manage_messages=True)
    @commands.has_permissions(manage_messages=True)
    @args.add_arg(
        "limit", type=int, default=5, nargs="?",
        help="The number of messages to clear"
    )
    @args.add_arg(
        "-b", "--before", type=int,
        help="Purge only messages before the message with the provided ID"
    )
    @args.add_arg(
        "-a", "--after", type=int,
        help="Purge only messages after the message with the provided ID"
    )
    @args.add_arg(
        "-u", "--user", type=commands.MemberConverter, action="append",
        help="Purge only messages from the given member (can be used"
             " multiple times to select multiple)"
    )
    @args.command(name="purge", aliases=["clear", "c"])
    async def purge_command(self, ctx, *, input):
        """Purge messages from the current channel"""
        purged = await ctx.channel.purge(
            limit=min(max(input.limit, 0), 2000),
            check=(lambda m: m.author in input.user
                   if input.user else lambda _: True),
            before=discord.Object(input.before) if input.before else None,
            after=discord.Object(input.after) if input.after else None
        )

        deleted = Counter([m.author for m in purged])
        embed = neo.Embed(
            title="Channel Purge Breakdown",
            description="\n".join(f"**{m.name}** {times} messages" for
                                  m, times in deleted.items())
        ).set_footer(text="This message will expire in 10 seconds")
        await ctx.send(embed=embed, delete_after=10)

    @commands.command(name="choose")
    async def choose_command(self, ctx, *, options: str):
        """
        Make a random choice from a set of options

        To separate each option, use a comma (`,`)
        Ex: `choose option a, option b, option c`
        """
        options = [opt.strip() for opt in options.split(",")]
        if len(options) < 2:
            raise ValueError("At least 2 options must be provided")

        data = Counter(random.choice(options) for _ in range(1000))

        table = Table()
        table.init_columns("Item", "Preference")
        for item, hits in data.most_common():
            table.add_row(shorten(item, 13), f"{(hits / 1000) * 100:.1f}%")
        rendered = table.display()

        embed = neo.Embed(
            description="```\n" + rendered + "\n```"
        ).add_field(
            name="Selection",
            value=f"`{shorten(data.most_common(1)[0][0], 250)}`"
        ).set_author(
            name=f"{ctx.author}'s choice results",
            icon_url=ctx.author.display_avatar
        )
        await ctx.send(embed=embed)

    # Information commands below

    @commands.hybrid_command(name="avatar", aliases=["av", "avy", "pfp"])
    async def avatar_command(self, ctx: NeoContext, *, user: discord.User | discord.Member = None):
        """Retrieves the avatar of yourself, or a specified user"""
        kwargs = {}
        embed = neo.Embed(description="")

        if not user:
            try:
                user = await ctx.guild.fetch_member(user or ctx.author.id)
            except (discord.HTTPException, AttributeError):
                user = await self.bot.fetch_user(user or ctx.author.id)

        if isinstance(user, neo.partials.PartialUser):
            try:
                user = await ctx.guild.fetch_member(user.id)
            except (discord.HTTPException, AttributeError):
                user = await user.fetch()

        if getattr(user, "guild_avatar", None) is not None:
            embed.set_thumbnail(url=user.guild_avatar.url)
            embed.description += "**View server avatar in browser**\n" \
                + get_browser_links(user.guild_avatar) + "\n\n"
            view = discord.ui.View()
            view.add_item(SwappableEmbedButton())
            kwargs["view"] = view

        avatar = user.avatar or user.default_avatar

        embed.description += "**View user avatar in browser**\n" \
            + get_browser_links(avatar)
        embed = embed.set_image(url=avatar).set_author(name=user)

        await ctx.send(embed=embed, **kwargs)

    @commands.hybrid_command(name="userinfo", aliases=["ui"])
    @discord.app_commands.describe(user="The user to get info about. If empty, gets your own info.")
    async def user_info_command(self, ctx: NeoContext, user: discord.Member | discord.User = None):
        """Retrieves information of yourself, or a specified user"""
        if not user:
            try:
                user = await ctx.guild.fetch_member(user or ctx.author.id)
            except (discord.HTTPException, AttributeError):
                user = await self.bot.fetch_user(user or ctx.author.id)

        if isinstance(user, neo.partials.PartialUser):
            try:
                user = await ctx.guild.fetch_member(user.id)
            except (discord.HTTPException, AttributeError):
                user = await user.fetch()

        embed = neo.Embed().set_thumbnail(url=user.display_avatar)
        flags = [v for k, v in BADGE_MAPPING.items() if k in
                 {flag.name for flag in user.public_flags.all()}]
        title = str(user)
        description = " ".join(flags) + ("\n" * bool(flags))
        description += f"**Created Account** <t:{int(user.created_at.timestamp())}:D>"

        if user.bot:
            title = (ICON_MAPPING["verified_bot_tag"] if user.public_flags
                     .verified_bot else ICON_MAPPING["bot_tag"]) + " " + title

        if isinstance(user, discord.Member):
            description += f"\n**Joined Server** <t:{int(user.joined_at.timestamp())}:D>"
            if user.id == ctx.guild.owner_id:
                title = "{0} {1}".format(ICON_MAPPING["guild_owner"], title)

        embed.title = title
        embed.description = description

        content = None
        if ctx.interaction and ctx.guild and not ctx.guild.default_role.permissions.external_emojis:
            content = ("Make sure @everyone has \"Use External Emoji\" permissions, otherwise"
                       " `userinfo` can't properly display icons!")

        await ctx.send(content=content, embed=embed)

    @commands.guild_only()
    @commands.hybrid_command(name="serverinfo", aliases=["si"])
    async def guild_info_command(self, ctx: NeoContext):
        """Retrieves information about the current server"""
        animated_emotes = len([e for e in ctx.guild.emojis if e.animated])
        static_emotes = len(ctx.guild.emojis) - animated_emotes

        embed = neo.Embed(
            title=f"{PREMIUM_ICON_MAPPING[ctx.guild.premium_tier]} {ctx.guild}",
            description=f"**Description** {ctx.guild.description}\n\n" * bool(ctx.guild.description)
            + f"**Created** <t:{int(ctx.guild.created_at.timestamp())}:D>"
            f"\n**Owner** <@{ctx.guild.owner_id}>"
            f"\n\n**Emotes** {static_emotes}/{ctx.guild.emoji_limit} static"
            f" | {animated_emotes}/{ctx.guild.emoji_limit} animated"
            f"\n**Filesize Limit** {round(ctx.guild.filesize_limit / 1_000_000)} MB"
            f"\n**Bitrate Limit** {round(ctx.guild.bitrate_limit / 1_000)} KB/s"
        ).set_thumbnail(url=ctx.guild.icon)

        content = None
        if ctx.interaction and ctx.guild and not ctx.guild.default_role.permissions.external_emojis:
            content = ("Make sure @everyone has \"Use External Emoji\" permissions, otherwise"
                       " `serverinfo` can't properly display icons!")

        await ctx.send(content=content, embed=embed)

    @commands.guild_only()
    @commands.hybrid_command(name="roleinfo", aliases=["ri"])
    @discord.app_commands.describe(role="The role to get info about.")
    async def role_info_command(self, ctx: NeoContext, *, role: discord.Role):
        """
        Retrives information about the given role

        The role can be specified by name, ID, or mention
        """
        associations = [desc for desc, _ in filter(
            lambda p: p[1](role), ASSOCIATION_FILTER)]
        embed = neo.Embed(
            title=role.name,
            description=f"**Created** <t:{int(role.created_at.timestamp())}:D>"
            + f"\n**Associations** {', '.join(associations)}" * bool(associations)
            + f"\n\n**Color** {str(role.colour).upper()}"
            f"\n**Mentionable** {role.mentionable}"
            f"\n**Hoisted** {role.hoist}"
            + f"\n**Icon** [View]({role.icon})" * bool(role.icon)
        ).set_thumbnail(url=role.icon or "")

        content = None
        if ctx.interaction and ctx.guild and not ctx.guild.default_role.permissions.external_emojis:
            content = ("Make sure @everyone has \"Use External Emoji\" permissions, otherwise"
                       " `roleinfo` can't properly display icons!")

        await ctx.send(content=content, embed=embed)

    @commands.hybrid_command(
        name="info",
        aliases=["about", "invite", "support", "source", "privacy"]
    )
    async def neo_info_command(self, ctx):
        """Show information about neo phoenix"""
        embed = neo.Embed(
            description=(
                "**neo Version** {0}"
                "\n**Server Count** {1}"
                "\n**Startup Time** <t:{2}>"
                "\n\n**Python Version** {3}"
                "\n**discord.py Version** {4}"
            ).format(
                neo.__version__,
                len(self.bot.guilds),
                self.bot.boot_time,
                py_version.split(" ", 1)[0],
                discord.__version__
            )
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar)
        embed.set_author(
            name=f"Developed by {self.appinfo.owner}",
            icon_url=self.appinfo.owner.display_avatar
        )
        await ctx.send(embed=embed, view=self.info_buttons())


async def setup(bot):
    await bot.add_cog(Utility(bot))

# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

import asyncio
import random
from collections import Counter
from functools import partial
from operator import attrgetter
from sys import version as py_version
from typing import Optional

import discord
import neo
from discord.ext import commands
from googletrans import LANGUAGES, Translator
from neo.classes.context import NeoContext
from neo.classes.formatters import Table
from neo.modules import DropdownMenu, EmbedPages, args, cse, dictionary
from neo.tools import shorten, parse_ids, deprecate

from .auxiliary.utility import (
    InfoButtons,
    SwappableEmbedButton,
    definitions_to_embed,
    get_translation_kwargs,
    result_to_embed,
    translate,
)

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
    "verified_bot_tag": "<:_:863197443083730959><:_:863197443565813780>",
}
PREMIUM_ICON_MAPPING = {
    0: "",
    1: "<:_:868138562690875452>",
    2: "<:_:868138562737041458>",
    3: "<:_:868138562913173564>",
}
ASSOCIATION_FILTER = [
    ("Server Default Role", discord.Role.is_default),
    ("Managed by Bot", discord.Role.is_bot_managed),
    ("Booster-Exclusive Role", discord.Role.is_premium_subscriber),
    ("Managed by Integration", discord.Role.is_integration),
]


def get_browser_links(avatar: discord.Asset):
    formats = ["PNG", "JPG", "WEBP"]
    if avatar.is_animated():
        formats.append("GIF")

    return " • ".join(
        f"[{fmt}]({avatar.with_format(fmt.lower())})" for fmt in formats  # type: ignore
    )


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

        self.bot.tree.context_menu(name="Show User Info")(
            self.user_info_context_command
        )
        self.bot.tree.context_menu(name="View Avatar")(self.avatar_context_command)
        self.bot.tree.context_menu(name="Show Message Info")(
            self.message_info_context_command
        )

        asyncio.create_task(self.__ainit__())

    async def __ainit__(self):
        await self.bot.wait_until_ready()

        # Since we wait for bot ready, this has to be true
        if not self.bot.user:
            raise RuntimeError("`self.bot.user` did not exist when it should have")

        # These both take a ClientSession, so we wait until ready so we can use the bot's
        self.google = cse.Search(
            key=self.bot.cfg["bot"]["cse_keys"],
            engine_id=self.bot.cfg["bot"]["cse_engine"],
            session=self.bot.session,
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
                url=self.bot.cfg["upstream_url"], label="Source Code", row=1
            ),
        ]
        self.info_buttons = partial(
            InfoButtons,
            self.privacy_embed,
            not self.appinfo.bot_public,
            buttons=buttons,
            presets=self.bot.cfg["invite_presets"],
            application_id=self.bot.user.id,
        )
        self.bot.add_view(self.info_buttons())

    # Create a fake slash command which directly invokes the help command
    # Uses `app_command_name` to falsify the command without interfering with
    # the actual command instance
    @discord.app_commands.command(name="help")
    @discord.app_commands.describe(command="The command to get help for")
    async def help_slash(
        self, interaction: discord.Interaction, *, command: Optional[str] = None
    ):
        """Displays help for the bot"""
        if self.bot.help_command is None:
            return

        ctx = await NeoContext.from_interaction(interaction)
        self.bot.help_command.context = ctx
        await self.bot.help_command.command_callback(ctx, command=command)

    @help_slash.autocomplete("command")
    async def help_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[discord.app_commands.Choice]:
        all_commands = set(
            [
                *map(attrgetter("qualified_name"), self.bot.walk_commands()),
                *map(attrgetter("qualified_name"), self.bot.tree.walk_commands()),
            ]
        )
        return [
            *map(
                lambda k: discord.app_commands.Choice(name=k, value=k),
                filter(lambda k: current in k, all_commands),
            )
        ][:25]

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
            pages, embed_auto_label=True, embed_auto_desc=True
        )
        await menu.start(ctx)

    @args.add_arg("word", nargs="+", help="The word to search a dictionary for")
    @args.command(name="define")
    @deprecate(reason="Use the `/define` slash command instead")
    async def dictionary_command(self, ctx, *, query):
        """Search the dictionary for a word's definition"""
        try:
            resp = await self.dictionary.define(" ".join(query.word))
        except dictionary.DefinitionError:
            raise RuntimeError("No definition found")

        embeds = []
        for word in resp.words:
            embeds.extend(definitions_to_embed(word))
        if not embeds:
            raise RuntimeError("No definition found")

        pages = EmbedPages(embeds)
        menu = DropdownMenu.from_pages(
            pages, embed_auto_label=True, embed_auto_desc=True
        )
        await menu.start(ctx)

    @discord.app_commands.command(name="define")
    @discord.app_commands.describe(term="The term to search the dictionary for")
    async def dictionary_app_command(self, interaction: discord.Interaction, term: str):
        """Search for a term's dictionary definition"""
        await interaction.response.defer(thinking=True)

        try:
            resp = await self.dictionary.define(term)
        except dictionary.DefinitionError:
            raise RuntimeError("No definition found")

        embeds = []
        for word in resp.words:
            embeds.extend(definitions_to_embed(word))
        if not embeds:
            raise RuntimeError("No definition found")

        pages = EmbedPages(embeds[:25])
        menu = DropdownMenu.from_pages(
            pages, embed_auto_label=True, embed_auto_desc=True
        )
        await menu.start(interaction)

    @commands.command(name="translate", aliases=["tr"], usage="[directive] <content>")
    @deprecate(reason="Use the `/translate` slash command instead")
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
            inline=False,
        )
        await ctx.send(embed=embed)

    @discord.app_commands.command(name="translate")
    @discord.app_commands.describe(
        source="The language to translate from. Default 'en'",
        destination="The language to translate to. Default 'en'",
        content="The content to translate",
    )
    @discord.app_commands.rename(source="from", destination="to")
    async def translate_app_command(
        self,
        interaction: discord.Interaction,
        content: str,
        source: Optional[str] = "en",
        destination: Optional[str] = "en",
    ):
        """
        Translate some text
        """
        await interaction.response.defer(thinking=True)

        translated = await translate(
            self.translator, content, dest=destination, src=source
        )
        embed = neo.Embed(
            description=f"**Source Language** `{source}` "
            f"[{LANGUAGES.get(translated.src, 'Auto-Detected').title()}]"
            f"\n**Destination Language** {LANGUAGES.get(translated.dest, 'Unknown').title()}"
        ).add_field(
            name="Translated Content",
            value=shorten(translated.text, 1024),
            inline=False,
        )
        await interaction.response.send_message(embeds=[embed])

    @commands.guild_only()
    @commands.bot_has_permissions(manage_messages=True)
    @commands.has_permissions(manage_messages=True)
    @args.add_arg(
        "limit", type=int, default=5, nargs="?", help="The number of messages to clear"
    )
    @args.add_arg(
        "-b",
        "--before",
        type=int,
        help="Purge only messages before the message with the provided ID",
    )
    @args.add_arg(
        "-a",
        "--after",
        type=int,
        help="Purge only messages after the message with the provided ID",
    )
    @args.add_arg(
        "-u",
        "--user",
        type=commands.MemberConverter,
        action="append",
        help="Purge only messages from the given member (can be used"
        " multiple times to select multiple)",
    )
    @args.command(name="purge", aliases=["c"])
    @deprecate(reason="Use the `/clear` slash command instead")
    async def purge_command(self, ctx, *, input):
        """Purge messages from the current channel"""
        purged = await ctx.channel.purge(
            limit=min(max(input.limit, 0), 2000),
            check=(lambda m: m.author in input.user if input.user else lambda _: True),
            before=discord.Object(input.before) if input.before else None,
            after=discord.Object(input.after) if input.after else None,
        )

        deleted = Counter([m.author for m in purged])
        embed = neo.Embed(
            title="Channel Purge Breakdown",
            description="\n".join(
                f"**{m.name}** {times} messages" for m, times in deleted.items()
            ),
        ).set_footer(text="This message will expire in 10 seconds")
        await ctx.send(embed=embed, delete_after=10)

    @discord.app_commands.command(name="clear")
    @discord.app_commands.guild_only()
    @discord.app_commands.describe(
        before="Delete only messages sent before this message ID or URL",
        after="Delete only messages sent after this message ID or URL",
        user="Delete only messages sent by this user",
        limit="The number of messages to delete",
    )
    @discord.app_commands.checks.bot_has_permissions(manage_messages=True)
    @discord.app_commands.checks.has_permissions(manage_messages=True)
    async def clear_app_command(
        self,
        interaction: discord.Interaction,
        before: Optional[str],
        after: Optional[str],
        user: Optional[discord.Member],
        limit: Optional[discord.app_commands.Range[int, 0, 2000]] = 5,
    ):
        """Clear messages from the current channel"""
        if not hasattr(interaction.channel, "purge"):
            raise RuntimeError("`clear` command called in invalid context")

        await interaction.response.defer(thinking=True)

        purged = await interaction.channel.purge(  # type: ignore
            limit=limit,
            check=(lambda m: m.author == user if user else True),
            before=discord.Object(parse_ids(before)[0]) if before else None,
            after=discord.Object(parse_ids(after)[0]) if after else None,
        )

        deleted = Counter([m.author for m in purged])
        embed = neo.Embed(
            title="Channel Purge Breakdown",
            description="\n".join(
                f"**{m.name}** {times} messages" for m, times in deleted.items()
            ),
        )
        await interaction.response.send_message(embeds=[embed])

    @commands.command(name="choose")
    async def choose_command(self, ctx, *, choices: str):
        """
        Make a random choice from a set of options

        To separate each option, use a comma (`,`)
        Ex: `choose option a, option b, option c`
        """
        options = [opt.strip() for opt in choices.split(",")]
        if len(options) < 2:
            raise ValueError("At least 2 options must be provided")

        data = Counter(random.choice(options) for _ in range(1000))

        table = Table()
        table.init_columns("Item", "Preference")
        for item, hits in data.most_common():
            table.add_row(shorten(item, 13), f"{(hits / 1000) * 100:.1f}%")
        rendered = table.display()

        embed = (
            neo.Embed(description="```\n" + rendered + "\n```")
            .add_field(
                name="Selection", value=f"`{shorten(data.most_common(1)[0][0], 250)}`"
            )
            .set_author(
                name=f"{ctx.author}'s choice results",
                icon_url=ctx.author.display_avatar,
            )
        )
        await ctx.send(embed=embed)

    # Information commands below

    @commands.hybrid_command(name="avatar", aliases=["av", "avy", "pfp"])
    @discord.app_commands.describe(
        user="The user to get the avatar of. Yourself if empty"
    )
    async def avatar_command(
        self, ctx: NeoContext, *, user: Optional[discord.User | discord.Member] = None
    ):
        """Retrieves the avatar of yourself, or a specified user"""
        kwargs = {}
        embed = neo.Embed()
        embed.description = ""

        if isinstance(user, neo.partials.PartialUser) or user is None:
            id = (user or ctx.author).id
            try:
                user_object = await ctx.guild.fetch_member(id)  # type: ignore
            except (discord.HTTPException, AttributeError):
                user_object = await self.bot.fetch_user(id)

        else:
            user_object = user

        if (
            isinstance(user_object, discord.Member)
            and user_object.guild_avatar is not None
        ):
            embed.set_thumbnail(url=user_object.guild_avatar.url)
            embed.description += (
                "**View server avatar in browser**\n"
                + get_browser_links(user_object.guild_avatar)
                + "\n\n"
            )
            view = discord.ui.View()
            view.add_item(SwappableEmbedButton())
            kwargs["view"] = view

        avatar = user_object.avatar or user_object.default_avatar

        embed.description += "**View user avatar in browser**\n" + get_browser_links(
            avatar
        )
        embed = embed.set_image(url=avatar).set_author(name=user_object)

        await ctx.send(embed=embed, **kwargs)

    # Context menu command added in __init__
    async def avatar_context_command(
        self, interaction: discord.Interaction, user: discord.Member | discord.User
    ):
        ctx = await NeoContext.from_interaction(interaction)
        ctx.interaction.namespace.ephemeral = True  # type: ignore
        await self.avatar_command(ctx, user=user)

    @commands.hybrid_command(name="userinfo", aliases=["ui"])
    @discord.app_commands.describe(user="The user to get info about. Yourself if empty")
    async def user_info_command(
        self, ctx: NeoContext, user: Optional[discord.Member | discord.User] = None
    ):
        """Retrieves information of yourself, or a specified user"""
        if isinstance(user, neo.partials.PartialUser) or user is None:
            id = (user or ctx.author).id
            try:
                user_object = await ctx.guild.fetch_member(id)  # type: ignore
            except (discord.HTTPException, AttributeError):
                user_object = await self.bot.fetch_user(id)

        else:
            user_object = user

        embed = neo.Embed().set_thumbnail(url=user_object.display_avatar)
        flags = [
            v
            for k, v in BADGE_MAPPING.items()
            if k in {flag.name for flag in user_object.public_flags.all()}
        ]
        title = str(user_object)
        description = " ".join(flags) + ("\n" * bool(flags))
        description += (
            f"**Created Account** <t:{int(user_object.created_at.timestamp())}:D>"
        )

        if user_object.bot:
            title = (
                (
                    ICON_MAPPING["verified_bot_tag"]
                    if user_object.public_flags.verified_bot
                    else ICON_MAPPING["bot_tag"]
                )
                + " "
                + title
            )

        if isinstance(user_object, discord.Member) and ctx.guild:
            description += (
                f"\n**Joined Server** <t:{int(user_object.joined_at.timestamp())}:D>"
                if user_object.joined_at
                else ""
            )
            if user_object.id == ctx.guild.owner_id:
                title = "{0} {1}".format(ICON_MAPPING["guild_owner"], title)

        embed.title = title
        embed.description = description

        content = None
        if (
            ctx.interaction
            and ctx.guild
            and not ctx.guild.default_role.permissions.external_emojis
        ):
            content = (
                'Make sure @everyone has "Use External Emoji" permissions, otherwise'
                " `userinfo` can't properly display icons!"
            )

        await ctx.send(content=content, embed=embed)

    # Context menu command added in __init__
    async def user_info_context_command(
        self, interaction: discord.Interaction, user: discord.Member | discord.User
    ):
        ctx = await NeoContext.from_interaction(interaction)
        ctx.interaction.namespace.ephemeral = True  # type: ignore
        await self.user_info_command(ctx, user)

    @commands.guild_only()
    @commands.hybrid_command(name="serverinfo", aliases=["si"])
    async def guild_info_command(self, ctx: NeoContext):
        """Retrieves information about the current server"""
        # The guild_only check guarantees that this will always work
        assert ctx.guild

        animated_emotes = len([e for e in ctx.guild.emojis if e.animated])
        static_emotes = len(ctx.guild.emojis) - animated_emotes

        embed = neo.Embed(
            title=f"{PREMIUM_ICON_MAPPING[ctx.guild.premium_tier]} {ctx.guild}",
            description=f"**Description** {ctx.guild.description}\n\n"
            * bool(ctx.guild.description)
            + f"**Created** <t:{int(ctx.guild.created_at.timestamp())}:D>"
            f"\n**Owner** <@{ctx.guild.owner_id}>"
            f"\n\n**Emotes** {static_emotes}/{ctx.guild.emoji_limit} static"
            f" | {animated_emotes}/{ctx.guild.emoji_limit} animated"
            f"\n**Filesize Limit** {round(ctx.guild.filesize_limit / 1_000_000)} MB"
            f"\n**Bitrate Limit** {round(ctx.guild.bitrate_limit / 1_000)} KB/s",
        ).set_thumbnail(url=ctx.guild.icon)

        content = None
        if (
            ctx.interaction
            and ctx.guild
            and not ctx.guild.default_role.permissions.external_emojis
        ):
            content = (
                'Make sure @everyone has "Use External Emoji" permissions, otherwise'
                " `serverinfo` can't properly display icons!"
            )

        await ctx.send(content=content, embed=embed)

    @commands.guild_only()
    @commands.hybrid_command(name="roleinfo", aliases=["ri"])
    @discord.app_commands.describe(role="The role to get info about")
    async def role_info_command(self, ctx: NeoContext, *, role: discord.Role):
        """
        Retrives information about the given role

        The role can be specified by name, ID, or mention
        """
        associations = [
            desc for desc, _ in filter(lambda p: p[1](role), ASSOCIATION_FILTER)
        ]
        embed = neo.Embed(
            title=role.name,
            description=f"**Created** <t:{int(role.created_at.timestamp())}:D>"
            + f"\n**Associations** {', '.join(associations)}" * bool(associations)
            + f"\n\n**Color** {str(role.colour).upper()}"
            f"\n**Mentionable** {role.mentionable}"
            f"\n**Hoisted** {role.hoist}"
            + f"\n**Icon** [View]({role.icon})" * bool(role.icon),
        ).set_thumbnail(url=role.icon or "")

        content = None
        if (
            ctx.interaction
            and ctx.guild
            and not ctx.guild.default_role.permissions.external_emojis
        ):
            content = (
                'Make sure @everyone has "Use External Emoji" permissions, otherwise'
                " `roleinfo` can't properly display icons!"
            )

        await ctx.send(content=content, embed=embed)

    @commands.hybrid_command(
        name="info", aliases=["about", "invite", "support", "source", "privacy"]
    )
    async def neo_info_command(self, ctx: NeoContext):
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
                discord.__version__,
            )
        )

        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar)
        embed.set_author(
            name=f"Developed by {self.appinfo.owner}",
            icon_url=self.appinfo.owner.display_avatar,
        )
        await ctx.send(embed=embed, view=self.info_buttons())

    async def message_info_context_command(
        self, interaction: discord.Interaction, message: discord.Message
    ):
        flags_str = ", ".join(
            f"`{flag[0]}`" for flag in filter(lambda p: p[1], message.flags)
        )

        raw_description = [
            f"**Message ID** {message.id}",
            f"**Author** {message.author}",
            f"**Created** <t:{message.created_at.timestamp():.0f}>",
            f"**Edited** <t:{message.edited_at.timestamp():.0f}>"
            if message.edited_at
            else None,
            f"\n**Is System Message** {message.is_system()}",
            f"**Message Type** `{message.type.name}`",
            f"**Message Flags** {flags_str}" if flags_str else "",
            f"\n**Pinned** {message.pinned}",
            f"**Is Interaction Response** {bool(message.interaction)}",
            f"**References A Message** {bool(message.reference)}",
            f"\n[**Jump URL**]({message.jump_url})",
        ]
        embed = neo.Embed(
            description="\n".join(filter(None, raw_description)),
        )

        if message.application:
            app = message.application
            embed.add_field(
                name="Associated Application",
                value="\n".join(
                    [
                        f"**Name** {app['name']}",
                        f"**ID** {app['id']}",
                        f"**Description** {shorten(app['description'], 30)}",
                    ]
                ),
                inline=False,
            )

        embed.set_thumbnail(url=message.author.display_avatar)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: neo.Neo):
    await bot.add_cog(Utility(bot))

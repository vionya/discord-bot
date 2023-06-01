# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
from __future__ import annotations

import asyncio
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import partial
from sys import version as py_version
from typing import Literal, Optional

import discord
from discord import app_commands
from discord.utils import format_dt
from googletrans import LANGUAGES, Translator

import neo
from neo.classes.app_commands import get_ephemeral
from neo.modules import DropdownMenu, EmbedPages, cse, dictionary
from neo.tools import parse_id, shorten, try_or_none
from neo.tools.formatters import Table, full_timestamp
from neo.tools.time_parse import parse_absolute, parse_relative

from .auxiliary.utility import (
    InfoButtons,
    SwappableEmbedButton,
    definitions_to_embed,
    get_browser_links,
    result_to_embed,
    translate,
)

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


class Utility(neo.Addon):
    """Various utility commands"""

    def __init__(self, bot: neo.Neo):
        self.bot = bot
        with open(bot.cfg["privacy_policy_path"]) as policy:
            header, body = policy.read().split("\n", 1)
            header = header.lstrip("# ")
            body = body.replace(
                "  \n", "\n"
            )  # Ensure proper formatting on mobile
        self.privacy_embed = neo.Embed(title=header, description=body)
        self.translator = Translator(raise_exception=True)

        self.bot.tree.context_menu(name="View Avatar")(
            self.avatar_context_command
        )
        self.bot.tree.context_menu(name="View Banner")(
            self.banner_context_command
        )
        self.bot.tree.context_menu(name="Show Message Info")(
            self.message_info_context_command
        )
        self.bot.tree.context_menu(name="Show Raw Content")(
            self.raw_msg_context_command
        )

        asyncio.create_task(self.__ainit__())

    async def __ainit__(self):
        await self.bot.wait_until_ready()

        # Since we wait for bot ready, this has to be true
        if not self.bot.user:
            raise RuntimeError(
                "`self.bot.user` did not exist when it should have"
            )

        # These both take a ClientSession, so we wait until ready so we can use the bot's
        self.google = cse.Search(
            keys=self.bot.cfg["bot"]["cse_keys"],
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
                url=self.bot.cfg["upstream"]["url"],
                label="Source Code",
                disabled=self.bot.cfg["upstream"]["disabled"],
                row=1,
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

    @app_commands.command(name="google")
    @app_commands.describe(query="The query to search for")
    async def google_command(
        self, interaction: discord.Interaction, query: str
    ):
        """Search Google for a query"""
        await self.google_command_callback(interaction, query)

    @app_commands.command(name="img")
    @app_commands.describe(query="The query to search for")
    async def google_image_command(
        self, interaction: discord.Interaction, query: str
    ):
        """Search Google Images for a query"""
        await self.google_command_callback(interaction, query, True)

    async def google_command_callback(
        self, interaction: discord.Interaction, query: str, image: bool = False
    ):
        resp = await self.google.search(query, image=image, results=30)

        embeds = [*map(result_to_embed, resp)]
        if not embeds:
            raise RuntimeError("Search returned no results")

        pages = EmbedPages(embeds)
        menu = DropdownMenu.from_pages(
            pages, embed_auto_label=True, embed_auto_desc=True
        )
        await menu.start(interaction)

    @app_commands.command(name="define")
    @app_commands.describe(term="The term to search the dictionary for")
    async def dictionary_app_command(
        self, interaction: discord.Interaction, term: str
    ):
        """Search for a term's dictionary definition"""
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

    @app_commands.command(name="translate")
    @app_commands.describe(
        source="The language to translate from. Default 'en'",
        destination="The language to translate to. Default 'en'",
        content="The content to translate",
    )
    @app_commands.rename(source="from", destination="to")
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

    @app_commands.command(name="clear")
    @app_commands.guild_only()
    @app_commands.describe(
        limit="The number of messages to delete",
        before="Delete only messages sent before this message ID or URL",
        after="Delete only messages sent after this message ID or URL",
        user="Delete only messages sent by this user",
    )
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear_app_command(
        self,
        interaction: discord.Interaction,
        limit: discord.app_commands.Range[int, 0, 2000],
        before: Optional[str],
        after: Optional[str],
        user: Optional[discord.Member],
    ):
        """Clear messages from the current channel"""
        if not hasattr(interaction.channel, "purge"):
            raise RuntimeError("`clear` command called in invalid context")
        assert isinstance(  # guaranteed by check above
            interaction.channel, discord.TextChannel | discord.VoiceChannel
        )

        ephemeral = get_ephemeral(interaction, interaction.namespace)
        before_o = (
            discord.Object(interaction.channel.last_message_id)
            if interaction.channel.last_message_id and not ephemeral
            else None
        )
        purged = await interaction.channel.purge(
            limit=limit,
            check=(lambda m: m.author == user if user else True),
            before=discord.Object(parse_id(before)) if before else before_o,
            after=discord.Object(parse_id(after)) if after else None,
        )

        deleted = Counter([m.author for m in purged])
        embed = neo.Embed(
            title="Channel Purge Breakdown",
            description="\n".join(
                f"**{m.name}** {times} messages" for m, times in deleted.items()
            ),
        )
        await interaction.response.send_message(embeds=[embed], ephemeral=True)

    @app_commands.command(name="choose")
    @app_commands.rename(
        opt_0="option-1",
        opt_1="option-2",
        opt_2="option-3",
        opt_3="option-4",
        opt_4="option-5",
    )
    @app_commands.describe(
        opt_0="The first choice to choose from",
        opt_1="The second choice to choose from",
        opt_2="The third choice to choose from (optional)",
        opt_3="The fourth choice to choose from (optional)",
        opt_4="The fifth choice to choose from (optional)",
    )
    async def choose_command(
        self,
        interaction: discord.Interaction,
        opt_0: str,
        opt_1: str,
        opt_2: Optional[str] = None,
        opt_3: Optional[str] = None,
        opt_4: Optional[str] = None,
    ):
        """Make a (pseudo-)random choice from up to 5 different options"""
        options = [
            opt.strip() for opt in (opt_0, opt_1, opt_2, opt_3, opt_4) if opt
        ]

        data = Counter(random.choice(options) for _ in range(1000))

        table = Table()
        table.init_columns("Item", "%")
        for item, hits in data.most_common():
            table.add_row(shorten(item, 19), f"{(hits / 1000) * 100:.1f}%")
        rendered = table.display()

        embed = (
            neo.Embed(description="```\n" + rendered + "\n```")
            .add_field(
                name="Selection",
                value=f"`{shorten(data.most_common(1)[0][0], 250)}`",
            )
            .set_author(
                name=f"{interaction.user}'s choice results",
                icon_url=interaction.user.display_avatar,
            )
        )
        await interaction.response.send_message(embed=embed)

    # Information commands below

    @app_commands.command(name="avatar")
    @app_commands.describe(
        user="The user to get the avatar of. Yourself if empty"
    )
    async def avatar_command(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.User | discord.Member] = None,
    ):
        """Retrieves the avatar of yourself, or a specified user"""
        kwargs = {}
        embed = neo.Embed()
        embed.description = ""

        if isinstance(user, neo.partials.PartialUser) or user is None:
            id = (user or interaction.user).id
            try:
                user_object = await interaction.guild.fetch_member(id)  # type: ignore
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

        embed.description += (
            "**View user avatar in browser**\n" + get_browser_links(avatar)
        )
        embed = embed.set_image(url=avatar).set_author(name=user_object)

        await interaction.response.send_message(embed=embed, **kwargs)

    @app_commands.guild_only()
    @app_commands.command(name="serverinfo")
    async def guild_info_command(self, interaction: discord.Interaction):
        """Retrieves information about the current server"""
        # The guild_only check guarantees that this will always work
        assert interaction.guild

        animated_emotes = len(
            [e for e in interaction.guild.emojis if e.animated]
        )
        static_emotes = len(interaction.guild.emojis) - animated_emotes

        embed = neo.Embed(
            title=f"{PREMIUM_ICON_MAPPING[interaction.guild.premium_tier]} {interaction.guild}",
            description=f"**Description** {interaction.guild.description}\n\n"
            * bool(interaction.guild.description)
            + f"**Created** <t:{int(interaction.guild.created_at.timestamp())}:D>"
            f"\n**Owner** <@{interaction.guild.owner_id}>"
            f"\n\n**Emotes** {static_emotes}/{interaction.guild.emoji_limit} static"
            f" | {animated_emotes}/{interaction.guild.emoji_limit} animated"
            f"\n**Filesize Limit** {round(interaction.guild.filesize_limit / 1_000_000)} MB"
            f"\n**Bitrate Limit** {round(interaction.guild.bitrate_limit / 1_000)} KB/s",
        ).set_thumbnail(url=interaction.guild.icon)

        content = None
        if not interaction.app_permissions.use_external_emojis:
            content = (
                'Make sure neo phoenix has "Use External Emoji" permissions,'
                " otherwise `serverinfo` can't properly display icons!"
            )

        await interaction.response.send_message(content=content, embed=embed)

    @app_commands.guild_only()
    @app_commands.command(name="roleinfo")
    @app_commands.describe(role="The role to get info about")
    async def role_info_command(
        self, interaction: discord.Interaction, *, role: discord.Role
    ):
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
            + f"\n**Associations** {', '.join(associations)}"
            * bool(associations)
            + f"\n\n**Color** {str(role.colour).upper()}"
            f"\n**Mentionable** {role.mentionable}"
            f"\n**Hoisted** {role.hoist}"
            + f"\n**Icon** [View]({role.icon})" * bool(role.icon),
        ).set_thumbnail(url=role.icon or "")

        content = None
        if not interaction.app_permissions.use_external_emojis:
            content = (
                'Make sure neo phoenix has "Use External Emoji" permissions,'
                " otherwise `roleinfo` can't properly display icons!"
            )

        await interaction.response.send_message(content=content, embed=embed)

    @app_commands.command(name="info")
    async def neo_info_command(self, interaction: discord.Interaction):
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
        await interaction.response.send_message(
            embed=embed, view=self.info_buttons()
        )

    @app_commands.command(name="timestamp")
    @app_commands.describe(
        when="The time the timestamp should point to, see /remind set for more",
        style="The style for format the timestamp with",
    )
    async def formatted_timestamp_command(
        self,
        interaction: discord.Interaction,
        when: str,
        style: Literal[
            "Short Time",
            "Long Time",
            "Short Date",
            "Long Date",
            "Short Date/Time",
            "Long Date/Time",
            "Relative Time",
        ] = "Short Date/Time",
    ):
        """
        Create a Discord timestamp from a human-readable input

        See the help documentation for `/remind set` to see how to format the
        input for `when`
        """
        tz = timezone.utc
        if interaction.user.id in self.bot.profiles:
            tz = self.bot.profiles[interaction.user.id].timezone or tz

        (time_data, _) = try_or_none(parse_relative, when) or parse_absolute(
            when, tz=tz
        )
        target = datetime.now(tz)

        if isinstance(time_data, timedelta):
            target += time_data
        else:
            target = time_data

        match style:
            case "Short Time":
                formatted = format_dt(target, style="t")
            case "Long Time":
                formatted = format_dt(target, style="T")
            case "Short Date":
                formatted = format_dt(target, style="d")
            case "Long Date":
                formatted = format_dt(target, style="D")
            case "Long Date/Time":
                formatted = format_dt(target, style="F")
            case "Relative Time":
                formatted = format_dt(target, style="R")
            case _:  # Short Date/Time is the default
                formatted = format_dt(target, style="f")

        await interaction.response.send_message(content=formatted)

    # CONTEXT MENU COMMANDS #

    # Context menu command added in __init__
    async def avatar_context_command(
        self,
        interaction: discord.Interaction,
        user: discord.Member | discord.User,
    ):
        setattr(interaction.namespace, "private", True)
        await self.avatar_command.callback(self, interaction, user)  # type: ignore

    async def banner_context_command(
        self,
        interaction: discord.Interaction,
        user: discord.Member | discord.User,
    ):
        user = await self.bot.fetch_user(user.id)
        if not user.banner:
            return await interaction.response.send_message(
                "User does not have a banner.", ephemeral=True
            )
        embed = (
            neo.Embed()
            .set_image(url=user.banner.with_size(4096).url)
            .set_author(name=user)
        )
        embed.description = (
            "**View banner in browser**\n"
            + get_browser_links(user.banner)
            + "\n\n"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def message_info_context_command(
        self, interaction: discord.Interaction, message: discord.Message
    ):
        flags_str = ", ".join(
            f"`{flag[0]}`" for flag in filter(lambda p: p[1], message.flags)
        )

        raw_description = [
            f"**ID** {message.id}",
            f"**Author** {message.author}",
            f"**Created** {full_timestamp(message.created_at.timestamp())}",
            f"**Edited** {full_timestamp(message.edited_at.timestamp())}"
            if message.edited_at
            else None,
            f"\n**Message Type** `{message.type.name}`",
            f"**Message Flags** {flags_str}" if flags_str else "",
            f"**Pinned** {message.pinned}",
        ]
        embed = neo.Embed(description="\n".join(filter(None, raw_description)))

        if message.application:
            app = message.application
            embed.add_field(
                name="Associated Application",
                value="\n".join(
                    [
                        f"**Name** {app.name}",
                        f"**ID** {app.id}",
                        f"**Description** {shorten(app.description, 30)}",
                    ]
                ),
                inline=False,
            )

        embed.set_thumbnail(url=message.author.display_avatar)

        view = discord.ui.View().add_item(
            discord.ui.Button(
                label="Jump to Message", url=message.jump_url, row=0
            )
        )
        if message.reference:
            view.add_item(
                discord.ui.Button(
                    label="Replied Message",
                    url=message.reference.jump_url,
                    row=0,
                )
            )

        await interaction.response.send_message(
            embed=embed, view=view, ephemeral=True
        )

    async def raw_msg_context_command(
        self, interaction: discord.Interaction, message: discord.Message
    ):
        if not message.content:
            return await interaction.response.send_message(
                "Message is empty", ephemeral=True
            )
        pages = neo.Pages(
            message.content.replace("`", "`\u200b"),
            1500,
            prefix="```\n",
            suffix="```",
            joiner="",
        )
        menu = neo.ButtonsMenu(pages)
        await menu.start(interaction, force_ephemeral=True)


async def setup(bot: neo.Neo):
    await bot.add_cog(Utility(bot))

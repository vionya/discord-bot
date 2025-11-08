# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 vionya
from __future__ import annotations

import asyncio
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import partial
from io import BytesIO
from sys import version as py_version
from typing import Literal, Optional
from zoneinfo import ZoneInfo, available_timezones

import discord
from aiohttp import FormData
from discord import app_commands, ui
from discord.utils import format_dt

import fuchsia
from fuchsia.classes.app_commands import get_ephemeral, no_defer
from fuchsia.modules import (
    ButtonsMenu,
    DropdownMenu,
    EmbedPages,
    ContainerPages,
    Interactors,
    cse,
    dictionary,
)
from fuchsia.tools import (
    iter_autocomplete,
    parse_id,
    shorten,
    try_or_none,
    ab_test,
)
from fuchsia.tools.decorators import singleton
from fuchsia.tools.formatters import full_timestamp, user_to_default_avatar
from fuchsia.tools.time_parse import parse_absolute, parse_relative

from .auxiliary.utility import (
    InfoButtons,
    StickerInfoView,
    AssetsView,
    definitions_to_embed,
    get_browser_links,
    get_choice,
    result_to_container,
    get_member_message_data,
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
TIMEZONE_STRS = available_timezones()
BADGE_MAPPING = {
    "active_developer": "<:_:1417957441840087140>",
    # "bot_http_interactions": "",  # TODO
    "bug_hunter": "<:_:1417956398012043274>",
    "bug_hunter_level_2": "<:_:1417956406170222755>",
    "discord_certified_moderator": "<:_:1417956389657120831>",
    "early_supporter": "<:_:1417956381654253578>",
    "hypesquad": "<:_:1417956335349141545>",
    "hypesquad_balance": "<:_:1417956365724553447>",
    "hypesquad_bravery": "<:_:1417956357780406383>",
    "hypesquad_brilliance": "<:_:1417956348317925550>",
    "partner": "<:_:1417956413917106216>",
    # "spammer": "",
    "staff": "<:_:1417956430627082260>",
    # "system": "",
    # "team_user": "",
    # "verified_bot": "",
    "verified_bot_developer": "<:_:1417956438445396192>",
}


class Utility(fuchsia.Addon):
    """Various utility commands"""

    def __init__(self, bot: fuchsia.Fuchsia):
        self.bot = bot
        with open(bot.cfg["privacy_policy_path"]) as policy:
            header, body = policy.read().split("\n", 1)
            header = header.lstrip("# ")
            body = body.replace(
                "  \n", "\n"
            )  # Ensure proper formatting on mobile
        self.privacy_embed = fuchsia.Embed(title=header, description=body)

        self.bot.tree.context_menu(name="View User Info")(
            self.userinfo_context_command
        )
        self.bot.tree.context_menu(name="View Avatar")(
            self.avatar_context_command
        )
        self.bot.tree.context_menu(name="View Banner")(
            self.banner_context_command
        )
        # self.bot.tree.context_menu(name="Show Message Info")(
        #     self.message_info_context_command
        # )
        # self.bot.tree.context_menu(name="Show Raw Content")(
        #     self.raw_msg_context_command
        # )
        self.bot.tree.context_menu(name="Inspect/Steal Sticker")(
            self.sticker_info_context_command
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
            not (await self.bot.application_info()).bot_public,
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
        resp = await self.google.search(query, image=image, results=10)

        components = [*map(lambda r: result_to_container(query, r), resp)]
        if not components:
            raise RuntimeError("Search returned no results")

        pages = ContainerPages(components)
        menu = DropdownMenu.from_pages(
            pages,
            option_labels=[result.title for result in resp],
            option_desc=[result.snippet for result in resp],
            private_interactors=Interactors.EVERYONE,
        )
        await menu.start(interaction)

    @app_commands.command(name="define")
    @app_commands.describe(
        term="The term to search the dictionary for",
        target_dict="The dictionary to search with",
    )
    @app_commands.rename(target_dict="dictionary")
    async def dictionary_command(
        self,
        interaction: discord.Interaction,
        term: str,
        target_dict: Literal["standard", "urban"] = "standard",
    ):
        """
        Search for a term's dictionary definition

        Use the `dictionary` parameter to choose between the standard[JOIN]
        dictionary and https://urbandictionary.com for definitions
        """
        try:
            match target_dict:
                case "standard":
                    resp = await self.dictionary.define_standard(term)
                case "urban":
                    resp = await self.dictionary.define_urban(term)
        except dictionary.DefinitionError as e:
            if e.status == 404:
                msg = "No definition found"
            else:
                msg = f"Something went wrong fetching a definition (status: {e.status})"
            raise RuntimeError(msg)

        components, label_descs = [], []
        for comp, (l, d) in definitions_to_embed(resp):
            components.append(comp)
            label_descs.append((l, d))
        if not components:
            raise RuntimeError("No definition found")

        pages = ContainerPages(components[:25])
        menu = DropdownMenu.from_pages(
            pages,
            option_labels=[label for (label, _) in label_descs],
            option_desc=[desc for (_, desc) in label_descs],
        )
        await menu.start(interaction)

    @app_commands.command(name="clear")
    @app_commands.allowed_contexts(
        guilds=True, dms=False, private_channels=False
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.describe(
        limit="The number of messages to delete",
        before="Delete only messages sent before this message ID or URL",
        after="Delete only messages sent after this message ID or URL",
        contains="Delete only messages containing this text",
        user="Delete only messages sent by this user",
    )
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    @no_defer
    async def clear_command(
        self,
        interaction: discord.Interaction,
        limit: discord.app_commands.Range[int, 0, 2000],
        before: Optional[str],
        after: Optional[str],
        contains: Optional[str],
        user: Optional[discord.Member],
    ):
        """Clear messages from the current channel - checks are ANDed together"""
        if not hasattr(interaction.channel, "purge"):
            raise RuntimeError("`clear` command called in invalid context")
        assert isinstance(  # guaranteed by check above
            interaction.channel,
            discord.TextChannel | discord.VoiceChannel | discord.Thread,
        )

        await interaction.response.defer(ephemeral=True)

        purged = await interaction.channel.purge(
            limit=limit,
            check=(
                lambda m: (m.author == user if user else True)
                and (contains in m.content if contains else True)
            ),
            before=discord.Object(parse_id(before)) if before else None,
            after=discord.Object(parse_id(after)) if after else None,
        )

        deleted = Counter([m.author for m in purged])
        embed = fuchsia.Embed(
            title="Channel Purge Breakdown",
            description="\n".join(
                f"**{m}** {times} messages" for m, times in deleted.items()
            ),
        )
        await interaction.followup.send(embeds=[embed], ephemeral=True)

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
        (selection, table) = get_choice(options)

        container = ui.Container(
            ui.TextDisplay("-# Choice Results"),
            ui.TextDisplay("```\n" + table + "\n```", id=67),
            ui.TextDisplay(f"**Selection** `{shorten(selection, 250)}`", id=68)
        )
        view = ui.LayoutView().add_item(container)
        await interaction.response.send_message(view=view)

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
        embed = fuchsia.Embed()
        embed.description = ""

        if isinstance(user, fuchsia.partials.PartialUser) or user is None:
            id = (user or interaction.user).id
            try:
                user_object = await interaction.guild.fetch_member(id)  # type: ignore
            except (discord.HTTPException, AttributeError):
                user_object = await self.bot.fetch_user(id)
        else:
            user_object = user

        avatar = user_object.avatar or user_object.default_avatar
        allow_save = get_ephemeral(interaction, interaction.namespace)
        if (
            isinstance(user_object, discord.Member)
            and user_object.guild_avatar is not None
        ):
            view = AssetsView(
                interaction.user.id,
                user_asset=avatar,
                guild_asset=user_object.guild_avatar,
                block_save=allow_save,
                asset_name="Avatar",
            )
            avatar = user_object.guild_avatar
        else:
            view = AssetsView(
                interaction.user.id,
                user_asset=avatar,
                guild_asset=None,
                block_save=allow_save,
                asset_name="Avatar",
            )

        embed.description += "**View in browser**\n" + get_browser_links(avatar)
        embed = embed.set_image(url=avatar).set_author(
            name=f"{user_object.display_name} ({user_object})"
        )

        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="banner")
    @app_commands.describe(
        user="The user to get the banner of. Yourself if empty"
    )
    async def banner_command(
        self,
        interaction: discord.Interaction,
        user: discord.User | discord.Member | None = None,
    ):
        """Retrieves the banner of yourself, or the specified user"""
        embed = fuchsia.Embed()
        embed.description = ""

        id = (user or interaction.user).id
        try:
            user_object = await interaction.guild.fetch_member(id)  # type: ignore
        except (discord.HTTPException, AttributeError):
            user_object = await self.bot.fetch_user(id)

        if (
            isinstance(user_object, discord.User) and user_object.banner is None
        ) or (
            isinstance(user_object, discord.Member)
            and user_object.display_avatar is None
        ):
            return await interaction.response.send_message(
                "User does not have a banner."
            )

        banner = user_object.banner
        allow_save = get_ephemeral(interaction, interaction.namespace)
        if (
            isinstance(user_object, discord.Member)
            and user_object.guild_banner is not None
        ):
            view = AssetsView(
                interaction.user.id,
                user_asset=banner,
                guild_asset=user_object.guild_banner,
                block_save=allow_save,
                asset_name="Banner",
            )
            banner = user_object.guild_banner
        else:
            view = AssetsView(
                interaction.user.id,
                user_asset=banner,
                guild_asset=None,
                block_save=allow_save,
                asset_name="Banner",
            )

        embed.description += "**View in browser**\n" + get_browser_links(banner)  # type: ignore
        embed = embed.set_image(url=banner).set_author(
            name=f"{user_object.display_name} ({user_object})"
        )

        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="serverinfo")
    @app_commands.allowed_contexts(
        guilds=True, dms=False, private_channels=False
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    async def guild_info_command(self, interaction: discord.Interaction):
        """Retrieves information about the current server"""
        # The guild_only check guarantees that this will always work
        assert interaction.guild

        all_emotes = await interaction.guild.fetch_emojis()
        animated_emotes = len([e for e in all_emotes if e.animated])
        static_emotes = len(all_emotes) - animated_emotes

        (message_count, _, _) = await get_member_message_data(
            self.bot.http, interaction.guild
        )

        embed = fuchsia.Embed(
            title=f"{PREMIUM_ICON_MAPPING[interaction.guild.premium_tier]} {interaction.guild}",
            description=f"**Description** {interaction.guild.description}\n\n"
            * bool(interaction.guild.description)
            + f"**Created** <t:{int(interaction.guild.created_at.timestamp())}:D>"
            f"\n**Owner** <@{interaction.guild.owner_id}>"
            f"\n\n**Emotes** {static_emotes}/{interaction.guild.emoji_limit} static"
            f" | {animated_emotes}/{interaction.guild.emoji_limit} animated"
            f"\n**Filesize Limit** {round(interaction.guild.filesize_limit / 1_000_000)} MB"
            f"\n**Bitrate Limit** {round(interaction.guild.bitrate_limit / 1_000)} KB/s"
            f"\n\n**Total Messages** {message_count:,}",
        ).set_thumbnail(url=interaction.guild.icon)

        content = None
        if not interaction.app_permissions.use_external_emojis:
            content = (
                'Make sure fuchsia has "Use External Emoji" permissions,'
                " otherwise `serverinfo` can't properly display icons!"
            )

        await interaction.response.send_message(content=content, embed=embed)

    @app_commands.command(name="roleinfo")
    @app_commands.allowed_contexts(
        guilds=True, dms=False, private_channels=False
    )
    @app_commands.allowed_installs(guilds=True, users=False)
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
        embed = fuchsia.Embed(
            title=role.name,
            description=f"**Created** <t:{int(role.created_at.timestamp())}:D>"
            + f"\n**Associations** {', '.join(associations)}"
            * bool(associations)
            + f"\n\n**Color** {str(role.colour).upper()}"
            f"\n**Mentionable** {role.mentionable}"
            f"\n**Hoisted** {role.hoist}"
            + f"\n**Icon** [View]({role.icon})" * bool(role.icon),
        ).set_thumbnail(url=role.icon or "")
        if role.color.value:
            embed.color = role.color

        content = None
        if not interaction.app_permissions.use_external_emojis:
            content = (
                'Make sure fuchsia has "Use External Emoji" permissions,'
                " otherwise `roleinfo` can't properly display icons!"
            )

        await interaction.response.send_message(content=content, embed=embed)

    @app_commands.command(name="info")
    async def fuchsia_info_command(self, interaction: discord.Interaction):
        """Show information about fuchsia"""
        appinfo = await self.bot.application_info()
        if team := appinfo.team:
            owner = team.owner or team.members[0]
        else:
            owner = appinfo.owner

        embed = fuchsia.Embed(
            description=(
                "**fuchsia Version** {0}"
                "\n**Server Install Count** {1}"
                "\n**User Install Count** {2}"
                "\n**Startup Time** <t:{3}>"
                "\n\n**Python Version** {4}"
                "\n**discord.py Version** {5}"
            ).format(
                fuchsia.__version__,
                appinfo.approximate_guild_count,
                appinfo.approximate_user_install_count,
                self.bot.boot_time,
                py_version.split(" ", 1)[0],
                discord.__version__,
            )
        ).set_author(
            name=f"Developed by {owner.display_name} ({owner})",
            icon_url=owner.avatar,
        )

        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar)
        await interaction.response.send_message(
            embed=embed, view=self.info_buttons()
        )

    @app_commands.command(name="upscale")
    @app_commands.describe(emoji="The emoji to upscale")
    async def upscale_emoji_command(
        self, interaction: discord.Interaction, emoji: str
    ):
        """Upscale a static or animated emoji and send the image"""
        partial = discord.PartialEmoji.from_str(emoji)
        if partial.is_unicode_emoji():
            raise ValueError("Only custom emojis can be upscaled")

        session = self.bot.session
        async with session.get(partial.url) as resp:
            emoji_data = await resp.read()

        content_type = "gif" if partial.animated else "png"
        (form := FormData()).add_field(
            name="data",
            value=emoji_data,
            filename=f"emoji.{content_type}",
            content_type=f"image/{content_type}",
        )

        dim = 256 if partial.animated else 512
        async with session.post(
            f"http://{self.bot.cfg['api']}/actions/resize",
            params={
                "width": dim,
                "height": dim,
                "frames": 250,
                "keep_aspect": "true",
            },
            data=form,
        ) as resp:
            upscaled_data = await resp.read()
            (width, height) = (
                resp.headers["x-width"],
                resp.headers["x-height"],
            )
            embed = (
                fuchsia.Embed(title=f"`{partial.name}` upscaled!")
                .set_image(url=f"attachment://upscaled.{content_type}")
                .set_footer(text=f"New size: {width}x{height} px")
            )
            if content_type == "gif":
                embed.description = (
                    "Note: only the first 250 frames of"
                    " this animated emoji have been upscaled"
                )

            await interaction.response.send_message(
                embed=embed,
                file=discord.File(
                    BytesIO(upscaled_data), f"upscaled.{content_type}"
                ),
            )

    @app_commands.command(name="steal")
    @app_commands.allowed_contexts(
        guilds=True, dms=False, private_channels=False
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(create_expressions=True)
    @app_commands.rename(source_emoji="emoji", new_name="name")
    @app_commands.describe(
        source_emoji="A custom emoji to steal to this server",
        file="An image file to add as an emoji",
        new_name="The name for this emoji",
    )
    async def create_emoji_command(
        self,
        interaction: discord.Interaction,
        source_emoji: str | None = None,
        file: discord.Attachment | None = None,
        new_name: app_commands.Range[str, 2, 32] | None = None,
    ):
        """
        Create a new custom emoji in the server

        You can either steal a custom emoji from another server with the[JOIN]
        `emoji` parameter, or create one from an image with the `file`[JOIN]
        parameter.

        The `name` parameter sets the name of the emoji. If stealing an[JOIN]
        emoji, this is optional, since the name of the emoji is used by[JOIN]
        default. If creating an emoji from a file, this is required.
        """
        assert interaction.guild

        if not (interaction.app_permissions.create_expressions):
            return await interaction.response.send_message(
                "fuchsia is missing the `Create Expressions` permission"
            )

        src = source_emoji or file
        if src is None:
            raise TypeError("You need to provide a source for the emoji")

        if isinstance(src, str):
            partial = discord.PartialEmoji.from_str(src.strip())
            if not partial.is_custom_emoji():
                raise ValueError("You need to provide a valid custom emoji")

            async with self.bot.session.get(partial.url) as resp:
                data = await resp.read()

            emoji = await interaction.guild.create_custom_emoji(
                name=new_name or partial.name, image=data
            )
        else:
            if not src.filename.lower().endswith(("jpg", "jpeg", "png", "gif")):
                raise ValueError("The file must be a JPEG, PNG, or GIF image")

            if src.size > 2_048_000:
                raise ValueError("The file can't be larger than 2048kb")

            if new_name is None:
                raise TypeError("You need to provide a name for this emoji")

            emoji = await interaction.guild.create_custom_emoji(
                name=new_name, image=await src.read()
            )

        await interaction.response.send_message(
            f"Successfully created emoji `{emoji.name}` {emoji}"
        )

    @app_commands.command(name="unicode")
    @app_commands.describe(content="The text to get the unicode data for")
    async def unicode_info_command(
        self, interaction: discord.Interaction, content: str
    ):
        """
        Lists the unicode codepoint and name of all characters in the input
        """
        output_lines = [
            "`{0}` | `U+{1:04X}` {2}".format(
                char, ord(char), unicodedata.name(char, "Unkown Character")
            )
            for char in set(content)
        ]
        menu = ButtonsMenu.from_iterable(
            output_lines, per_page=10, use_container=True
        )
        await menu.start(interaction)

    @singleton
    class TimeUtilities(app_commands.Group, name="time"):
        """Utility commands for doing stuff with time"""

        addon: Utility

        @iter_autocomplete(TIMEZONE_STRS, param="source_tz")
        @app_commands.command(name="in")
        @app_commands.describe(source_tz="The timezone to get the time in")
        @app_commands.rename(source_tz="timezone")
        async def time_in_command(
            self, interaction: discord.Interaction, source_tz: str
        ):
            """Get the current time in a given timezone"""
            if source_tz not in TIMEZONE_STRS:
                raise ValueError("Invalid timezone provided")
            tz = ZoneInfo(source_tz)
            target = datetime.now(tz)
            time_info = target.strftime(
                "**Time** %H:%M:%S (%I:%M %p)\n**Date** %d %B, %Y"
            )
            await interaction.response.send_message(
                embed=fuchsia.Embed(
                    title=f"Time at {source_tz}", description=time_info
                )
            )

        @iter_autocomplete(TIMEZONE_STRS, param="source_tz")
        @app_commands.command(name="stamp")
        @app_commands.describe(
            when="The time the timestamp should point to, see /remind set for more",
            style="The style for format the timestamp with",
            source_tz="The timezone to set absolute timestamps in",
        )
        @app_commands.rename(source_tz="timezone")
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
            source_tz: str | None = None,
        ):
            """
            Create a Discord timestamp from a human-readable input

            See the help documentation for `/remind set` to see how to format the
            input for `when`
            """
            if source_tz is not None:
                if source_tz not in TIMEZONE_STRS:
                    raise ValueError("Invalid timezone provided")
                tz = ZoneInfo(source_tz)
            else:
                tz = timezone.utc
                if interaction.user.id in self.addon.bot.profiles:
                    tz = (
                        self.addon.bot.profiles[interaction.user.id].timezone
                        or tz
                    )

            (time_data, _) = try_or_none(
                parse_relative, when
            ) or parse_absolute(when, tz=tz)
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

    @app_commands.command(name="userinfo")
    @app_commands.describe(user="The user to get info for, yourself if empty")
    async def userinfo_command(
        self,
        interaction: discord.Interaction,
        user: discord.Member | discord.User | None = None,
    ):
        """
        Retrieves info on the specified user, or on yourself.
        """
        if isinstance(user, fuchsia.partials.PartialUser) or user is None:
            id = (user or interaction.user).id
        else:
            id = user.id

        # we need to fetch the user every time to have the required info
        try:
            user_object = await interaction.guild.fetch_member(id)  # type: ignore
        except (discord.HTTPException, AttributeError):
            user_object = await self.bot.fetch_user(id)

        avatar = user_object.display_avatar.url
        # unsure about this so A/B testing with it until i decide
        if (
            ab_test("circle_pfp", interaction.user.id, 0.1)
            and not user_object.display_avatar.is_animated()
        ):
            data = (
                await user_object.display_avatar.with_format("png")
                .with_size(256)
                .read()
            )
            (form := FormData()).add_field(
                name="data",
                value=data,
                filename="av.png",
                content_type="image/png",
            )
            async with self.bot.session.post(
                f"http://{self.bot.cfg['api']}/actions/circlize?dim=256",
                data=form,
            ) as resp:
                avatar = discord.File(
                    BytesIO(await resp.read()), "circle_avatar.png"
                )

        is_member = isinstance(user_object, discord.Member)
        container = ui.Container(
            ui.Section(
                f"-# {user_object.display_name}"
                + (
                    f" ({user_object})"
                    if user_object.display_name != str(user_object)
                    else ""
                ),
                "### Primary Info"
                + "\n"
                + " ".join(
                    BADGE_MAPPING[badge]
                    for badge, owned in user_object.public_flags
                    if owned
                )
                + f"\n**User ID** `{user_object.id}`"
                + f"\n**Account Made** {format_dt(user_object.created_at)}"
                + (
                    f"\n**Accent Color** `#{user_object.accent_color.value:X}`"
                    if user_object.accent_color
                    else ""
                )
                + f"\n**Default Avatar** {user_to_default_avatar(user_object)}",
                accessory=ui.Thumbnail(avatar),
            ),
        )

        if user_object.accent_color:
            container.accent_color = user_object.accent_color

        if is_member:
            assert interaction.guild is not None
            assert isinstance(user_object, discord.Member)
            assert user_object.joined_at

            (
                total_messages,
                first_message,
                first_link,
            ) = await get_member_message_data(
                self.bot.http, interaction.guild, user_object
            )
            container.add_item(
                ui.TextDisplay(
                    f"### Info in {interaction.guild}"
                    + (
                        f"\n<:server_owner:1417956422225756220> **owns this server**"
                        if interaction.guild.owner_id == user_object.id
                        else ""
                    )
                    + f"\n**Joined Server** {format_dt(user_object.joined_at)}"
                    + (
                        f"\n**First Message** {format_dt(first_message)}"
                        if first_message
                        else ""
                    )
                    + f"\n**Total Messages** {total_messages:,}"
                ),
            )

            # idk if i should leave this in or not so i'll A/B test on it lol
            if ab_test("see_first_message", interaction.user.id) and first_link:
                container.add_item(
                    ui.ActionRow(
                        ui.Button(url=first_link, label="See first message")
                    )
                )

        await interaction.response.send_message(
            view=ui.LayoutView(timeout=0).add_item(container),
            files=[avatar] if isinstance(avatar, discord.File) else [],
        )

    # CONTEXT MENU COMMANDS #

    # Context menu command added in __init__
    async def userinfo_context_command(
        self,
        interaction: discord.Interaction,
        user: discord.Member | discord.User,
    ):
        """
        Shows information about the selected user

        This command is functionally the same as using the `/userinfo`[JOIN]
        command, but is possibly more convenient. Additionally, the output[JOIN]
        of this command will only ever be visible to you.
        """
        setattr(interaction.namespace, "private", True)
        await self.userinfo_command.callback(self, interaction, user)  # type: ignore

    async def avatar_context_command(
        self,
        interaction: discord.Interaction,
        user: discord.Member | discord.User,
    ):
        """
        Shows the selected user's avatar

        This command is functionally the same as using the `/avatar`[JOIN]
        command, but is possibly more convenient. Additionally, the output[JOIN]
        of this command will only ever be visible to you.
        """
        setattr(interaction.namespace, "private", True)
        await self.avatar_command.callback(self, interaction, user)  # type: ignore

    async def banner_context_command(
        self,
        interaction: discord.Interaction,
        user: discord.Member | discord.User,
    ):
        """
        Shows the selected user's banner

        This command is functionally the same as using the `/banner`[JOIN]
        command, but is possibly more convenient. Additionally, the output[JOIN]
        of this command will only ever be visible to you.
        """
        setattr(interaction.namespace, "private", True)
        await self.banner_command.callback(self, interaction, user)  # type: ignore

    async def message_info_context_command(
        self, interaction: discord.Interaction, message: discord.Message
    ):
        """View information about the selected message"""
        flags_str = ", ".join(
            f"`{flag[0]}`" for flag in filter(lambda p: p[1], message.flags)
        )

        raw_description = (
            f"**ID** {message.id}",
            f"**Author** {message.author}",
            f"**Created** {full_timestamp(message.created_at.timestamp())}",
            (
                f"**Edited** {full_timestamp(message.edited_at.timestamp())}"
                if message.edited_at
                else None
            ),
            f"\n**Message Type** `{message.type.name}`",
            f"**Message Flags** {flags_str}" if flags_str else "",
            f"**Pinned** {message.pinned}",
        )
        embed = fuchsia.Embed(
            description="\n".join(filter(None, raw_description))
        )

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
        """View the raw content of the selected message"""
        if not message.content:
            return await interaction.response.send_message(
                "Message is empty", ephemeral=True
            )
        pages = fuchsia.Pages(
            message.content.replace("`", "`\u200b"),
            1500,
            prefix="```\n",
            suffix="```",
            joiner="",
        )
        menu = fuchsia.ButtonsMenu(pages)
        await menu.start(interaction, force_ephemeral=True)

    async def sticker_info_context_command(
        self, interaction: discord.Interaction, message: discord.Message
    ):
        """
        Gets sticker info, and also lets you steal a sticker from another[JOIN]
        server and add it to this one

        This is a convenient (but sometimes finicky) shortcut to easily[JOIN]
        steal stickers.

        It will work if all of these conditions are true:
        - fuchsia has the `Create Expressions` and `Manage Expressions`[JOIN]
        permissions
        - The selected message actually has a sticker attached
        - The sticker is not a default Discord sticker
        - The server has available sticker slots
        - The sticker has not been deleted on its original server
        - The server and sticker need to be discoverable

        If the stars align (which they tend to), fuchsia will successfully[JOIN]
        steal the desired sticker and add it to your server.
        """
        # if the message has no stickers on it, there's no point in proceeding
        if (
            message.reference
            and message.reference.type == discord.MessageReferenceType.forward
        ):
            message = message.message_snapshots[0]  # type: ignore

        if not message.stickers:
            return await interaction.response.send_message(
                "That message has no sticker!", ephemeral=True
            )

        # get the base sticker
        sticker = message.stickers[0]

        desc = [
            f"**Name** {sticker.name}",
            f"**Image Format** `{sticker.format.name}`",
            f"[**Sticker URL**]({sticker.url})",
        ]

        view = discord.utils.MISSING
        try:
            # fetch the entire sticker data
            sticker_full = await message.stickers[0].fetch()
            desc.insert(
                1,
                f"**Description** {sticker_full.description or 'No description'}",
            )

            if isinstance(sticker_full, discord.GuildSticker):
                desc.extend(
                    [
                        "\n*This sticker comes from a server*",
                        f"**Associated Emoji** `{sticker_full.emoji}`",
                    ]
                )
            if interaction.context.guild:
                view = StickerInfoView(sticker_full, interaction)
        except:
            # i don't actually care what happens if this fails
            # it just means there was some sort of issue with fetching the
            # sticker, and there's still useful information that can be gained
            # from a partial sticker
            pass

        embed = fuchsia.Embed(
            title="Sticker Info", description="\n".join(desc)
        ).set_footer(text=f"Sticker ID: {sticker.id}")
        if sticker.format != discord.StickerFormatType.lottie:
            embed.set_image(url=sticker.url)

        await interaction.response.send_message(
            embed=embed, ephemeral=True, view=view
        )


async def setup(bot: fuchsia.Fuchsia):
    await bot.add_cog(Utility(bot))

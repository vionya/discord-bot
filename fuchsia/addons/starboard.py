# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 sardonicism-04
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands

import fuchsia
from fuchsia.classes.containers import TimedCache, TimedSet
from fuchsia.modules import ButtonsMenu
from fuchsia.tools import (
    add_setting_autocomplete,
    convert_setting,
    singleton,
    parse_id,
    shorten,
    guild_only,
)
from fuchsia.tools.checks import is_valid_starboard_env

from .auxiliary.starboard import SETTINGS_MAPPING, ChangeSettingButton

if TYPE_CHECKING:
    from asyncpg import Pool


class Star:
    __slots__ = ("message_id", "starboard_message", "stars", "forced")

    def __init__(
        self,
        *,
        message_id: int,
        starboard_message: discord.PartialMessage,
        stars: int,
        forced: bool,
    ):
        self.message_id = message_id
        self.starboard_message = starboard_message
        self.stars = stars
        self.forced = forced

    def __repr__(self):
        return (
            "<{0.__class__.__name__} stars={0.stars} "
            "message_id={0.message_id}>".format(self)
        )

    async def edit(self, **kwargs):
        await self.starboard_message.edit(**kwargs)


class Starboard:
    __slots__ = (
        "channel",
        "threshold",
        "super_mult",
        "format",
        "max_days",
        "emoji",
        "ignored",
        "star_ids",
        "cached_stars",
        "lock",
        "pool",
    )

    def __init__(
        self,
        *,
        channel: Optional[discord.TextChannel],
        threshold: int,
        super_mult: int,
        format: str,
        max_days: int,
        emoji: discord.PartialEmoji,
        ignored: set[int],
        pool: Pool,
    ):
        self.channel = channel
        self.threshold = threshold
        self.super_mult = super_mult
        self.format = format
        self.max_days = max_days
        self.emoji = emoji
        self.ignored = ignored

        # Don't store star IDs forever
        self.star_ids = TimedSet[int](timeout=1000)

        # Use timed cache so that stars are not persisting for
        # longer than they reasonably should be
        self.cached_stars = TimedCache[int, Star](300)
        self.lock = asyncio.Lock()
        self.pool = pool

    async def exists(self, id: int) -> bool:
        """
        Checks whether a star exists in this starboard

        If the star ID already exists in the internal cache, returns True
        immediately. Otherwise, the database is queried for the given star
        ID. If a match is found, the star ID is added to the internal cache
        and this function returns True. Otherwise, returns False.
        """
        if id in self.star_ids:
            return True
        if await self.pool.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM stars
                WHERE message_id=$1
            )
            """,
            id,
        ):
            self.star_ids.add(id)
            return True
        return False

    async def get_star(
        self, id: int, *, from_starboard_message: bool = False
    ) -> Star | None:
        if not self.channel:
            return None

        if from_starboard_message is False and id in self.cached_stars:
            return self.cached_stars[id]

        query = "SELECT * FROM stars WHERE {0}=$1".format(
            "starboard_message_id"
            if from_starboard_message is True
            else "message_id"
        )
        star_data = await self.pool.fetchrow(query, id)

        if star_data:
            starboard_msg = self.channel.get_partial_message(
                star_data["starboard_message_id"]
            )
            star = Star(
                message_id=star_data["message_id"],
                starboard_message=starboard_msg,
                stars=star_data["stars"],
                forced=star_data["forced"],
            )
            self.star_ids.add(star_data["message_id"])
            self.cached_stars[star_data["message_id"]] = star
            return star
        return None

    async def create_star(
        self, message: discord.Message, stars: int, *, forced=False
    ):
        if (
            not message.guild
            or not self.channel
            or any([await self.exists(message.id), self.lock.locked()])
        ):
            return

        assert isinstance(
            message.channel, discord.abc.GuildChannel | discord.Thread
        )

        async with self.lock:
            try:
                # fetch member to get their guild display name and avatar
                author = await message.guild.fetch_member(message.author.id)
            except discord.DiscordException:
                # make sure to have a fallback in case something goes wrong
                author = message.author

            embed = (
                fuchsia.Embed(description="", timestamp=message.created_at)
                .set_footer(text=f"#{message.channel.name}")
                .set_author(
                    name=f"{author.display_name} ({message.author})",
                    icon_url=author.display_avatar,
                )
            )

            view = discord.ui.View(timeout=0)
            view.add_item(
                discord.ui.Button(url=message.jump_url, label="Jump to message")
            )

            if isinstance(message.channel, discord.Thread):
                assert message.channel.parent
                embed.set_footer(
                    text=f"#{message.channel.parent.name} > {message.channel.name}"
                )

            if message.stickers:
                embed.add_field(
                    name=f"Stickers [x{len(message.stickers)}]",
                    value="\n".join(
                        f"`{sticker.name}`" for sticker in message.stickers
                    ),
                    inline=False,
                )

            if (ref := message.reference) and isinstance(
                ref.resolved, discord.Message
            ):
                # if the replied-to user and author are the same, save a req
                if ref.resolved.author.id == author.id:
                    reply_display = "self"
                else:
                    # otherwise we have to fetch it
                    try:
                        replied_to = await message.guild.fetch_member(
                            ref.resolved.author.id
                        )
                    except discord.DiscordException:
                        replied_to = ref.resolved.author
                    reply_display = (
                        f"{replied_to.display_name} ({ref.resolved.author})"
                    )

                embed.add_field(
                    name="Replying to " + reply_display,
                    value=shorten(ref.resolved.content, 500),
                    inline=False,
                )
                view.add_item(
                    discord.ui.Button(url=ref.jump_url, label="Jump to reply")
                )

            if message.content:
                if ref:
                    embed.add_field(
                        name=author.display_name,
                        value=shorten(message.content, 1024),
                        inline=False,
                    )
                else:
                    embed.description = shorten(message.content, 1900)

            if attachments := (*message.attachments, *message.embeds):
                if not embed.image:
                    prev = attachments[0]
                    # Don't add spoilered images to embed
                    if not getattr(prev, "filename", "").startswith("SPOILER_"):
                        embed.set_image(url=prev.url)

                embed.add_field(
                    name=f"Attachments/Embeds [x{len(attachments)}]",
                    value="\n".join(
                        # don't want the message to look weird if there's not
                        # a URL associated with an embed (e.g. it's a bot-
                        # generated embed)
                        (
                            "[`{fn}`]({url})" if attachment.url else "{fn}"
                        ).format(
                            fn=getattr(attachment, "filename", "Embed"),
                            url=attachment.url,
                        )
                        for attachment in attachments
                    ),
                    inline=False,
                )

            content = (
                "*This message was force-starred by a moderator*"
                if forced
                else self.format.format(stars=stars)
            )
            starboard_message = await self.channel.send(
                content, embed=embed, view=view
            )
            star = Star(
                message_id=message.id,
                stars=stars,
                starboard_message=starboard_message,
                forced=forced,
            )

            await self.pool.execute(
                """
                INSERT INTO stars (
                    guild_id,
                    message_id,
                    channel_id,
                    stars,
                    starboard_message_id,
                    forced
                ) VALUES (
                    $1, $2, $3, $4, $5, $6
                )
                """,
                message.guild.id,
                message.id,
                message.channel.id,
                stars,
                star.starboard_message.id,
                forced,
            )

            self.star_ids.add(message.id)
            self.cached_stars[message.id] = star
            return star

    async def delete_star(self, id: int):
        star = await self.get_star(id)
        if star:
            await star.starboard_message.delete()
            del self.cached_stars[id]

        await self.pool.execute("DELETE FROM stars WHERE message_id=$1", id)
        self.star_ids.remove(id)
        return star

    async def edit_star(self, id: int, stars: int):
        star = await self.get_star(id)
        if not star:
            return await self.delete_star(id)

        star.stars = stars

        try:
            await star.edit(content=self.format.format(stars=star.stars))
        except (
            discord.NotFound
        ):  # Delete star from records if its message has been deleted
            return await self.delete_star(id)

        await self.pool.execute(
            """
            UPDATE stars
            SET stars=$1
            WHERE message_id=$2
            """,
            star.stars,
            star.message_id,
        )
        return star


@guild_only
class StarboardAddon(
    fuchsia.Addon,
    name="Starboard",
    app_group=True,
    group_name="starboard",
    group_description="Starboard management commands",
):
    """
    Manages your server's starboard

    If `starboard` is set to False in server
    settings, none of the commands from this category
    will be accessible
    """

    def __init__(self, bot: fuchsia.Fuchsia):
        self.bot = bot
        self.ready = False
        self.starboards: dict[int, Starboard] = {}

        guild_only(
            self.bot.tree.context_menu(name="Toggle Forced Starboard")(
                self.force_star_ctx
            )
        )

        asyncio.create_task(self.__ainit__())

    async def __ainit__(self):
        await self.bot.wait_until_ready()

        # Setup starboards
        starboard_settings = {}
        for record in await self.bot.db.fetch("SELECT * FROM starboards"):
            starboard_settings[record["guild_id"]] = record

        for guild_id in self.bot.configs.keys():
            if guild_id not in [*starboard_settings.keys()]:
                continue

            settings = starboard_settings[guild_id]
            self.starboards[guild_id] = await self.create_starboard(
                guild_id, settings
            )
        self.ready = True

        # Initialize settings
        for col_name in SETTINGS_MAPPING.keys():
            col_desc = await self.bot.db.fetchval(
                """
                SELECT get_column_description(
                    $1, 'starboards', $2
                )
                """,
                self.bot.cfg["database"]["database"],
                col_name,
            )
            SETTINGS_MAPPING[col_name]["description"] = col_desc

    async def create_starboard(self, guild_id, starboard_settings):
        channel = self.bot.get_channel(starboard_settings["channel"])

        return Starboard(
            channel=channel,  # type: ignore
            threshold=starboard_settings["threshold"],
            super_mult=starboard_settings["super_mult"],
            format=starboard_settings["format"],
            max_days=starboard_settings["max_days"],
            emoji=discord.PartialEmoji.from_str(starboard_settings["emoji"]),
            ignored=set(starboard_settings["ignored"]),
            pool=self.bot.db,
        )

    # Sect: Event handling

    def predicate(self, starboard: Starboard, payload):
        if starboard is None or starboard.channel is None:
            return False
        checks = [
            not self.bot.configs[starboard.channel.guild.id].starboard,
            payload.channel_id == starboard.channel.id,
            # (datetime.now(timezone.utc) - discord.Object(payload.message_id)
            #  .created_at).days > starboard.max_days
        ]
        check_ignored = [  # Ensure the channel/message isn't ignored
            payload.message_id in starboard.ignored,
            payload.channel_id in starboard.ignored,
        ]
        checks.append(any(check_ignored))
        return not any(checks)

    @staticmethod
    def reaction_check(starboard: Starboard, emoji):
        if isinstance(emoji, str):
            emoji = discord.PartialEmoji.from_str(emoji)
        return emoji == starboard.emoji

    @fuchsia.Addon.listener("on_raw_reaction_add")
    @fuchsia.Addon.listener("on_raw_reaction_remove")
    async def handle_individual_reaction(
        self, payload: discord.RawReactionActionEvent
    ):
        if payload.guild_id not in self.starboards or not payload.guild_id:
            return
        starboard = self.starboards[payload.guild_id]

        if not self.predicate(starboard, payload):
            return

        if not await starboard.exists(payload.message_id):
            if (
                datetime.now(timezone.utc)
                - discord.Object(payload.message_id).created_at
            ).days > starboard.max_days:
                return

            channel = self.bot.get_channel(payload.channel_id)
            if not (
                isinstance(channel, discord.abc.Messageable)
                and not isinstance(channel, discord.GroupChannel)
            ):
                return
            message = await channel.fetch_message(payload.message_id)

            star_reaction = next(
                filter(
                    lambda r: self.reaction_check(starboard, r.emoji),
                    message.reactions,
                ),
                None,
            )
            if star_reaction is None:
                return

            # total reactions is a function of the normal count and the super
            # reaction count multiplied by the super reaction multiplier
            reaction_count = star_reaction.normal_count + (
                star_reaction.burst_count * starboard.super_mult
            )
            if reaction_count < starboard.threshold:
                return

            star = await starboard.create_star(message, reaction_count)
            if not star:
                return

        else:
            if not self.reaction_check(starboard, payload.emoji):
                return

            star = await starboard.get_star(payload.message_id)
            # if the star doesn't exist or it's been force-starred then skip
            if star is None or star.forced is True:
                return

            multiplier = starboard.super_mult if payload.burst else 1
            match payload.event_type:
                case "REACTION_ADD":
                    star.stars += 1 * multiplier
                case "REACTION_REMOVE":
                    star.stars -= 1 * multiplier

            if star.stars < starboard.threshold:
                await starboard.delete_star(star.message_id)
            else:
                await starboard.edit_star(star.message_id, star.stars)

    @fuchsia.Addon.listener("on_raw_reaction_clear")
    @fuchsia.Addon.listener("on_raw_reaction_clear_emoji")
    @fuchsia.Addon.listener("on_raw_message_delete")
    async def handle_terminations(
        self,
        payload: (
            discord.RawReactionClearEvent
            | discord.RawReactionClearEmojiEvent
            | discord.RawMessageDeleteEvent
        ),
    ):
        if payload.guild_id not in self.starboards or not payload.guild_id:
            return
        starboard = self.starboards[payload.guild_id]

        if not self.predicate(starboard, payload):
            return

        if isinstance(payload, discord.RawReactionClearEmojiEvent):
            if not self.reaction_check(starboard, payload.emoji):
                return

        if await starboard.exists(payload.message_id):
            await starboard.delete_star(payload.message_id)

    @fuchsia.Addon.listener("on_guild_channel_delete")
    async def handle_starboard_channel_delete(
        self, channel: discord.abc.GuildChannel
    ):
        if channel.guild.id not in self.starboards:
            return

        starboard = self.starboards[channel.guild.id]
        if channel.id == getattr(starboard.channel, "id", None):
            await self.bot.db.execute(
                "DELETE FROM stars WHERE guild_id=$1", channel.guild.id
            )
            starboard.cached_stars.clear()
            starboard.channel = None

    @fuchsia.Addon.recv("config_update")
    async def handle_starboard_setting(self, guild, settings):
        if settings.starboard is True:
            if guild.id in self.starboards:
                return

            # Create a new starboard if one doesn't exist
            starboard_data = await self.bot.db.fetchrow(
                """
                INSERT INTO starboards (
                    guild_id
                ) VALUES ($1)
                RETURNING *
                """,
                guild.id,
            )

            self.starboards[guild.id] = await self.create_starboard(
                guild.id, starboard_data
            )

    @fuchsia.Addon.recv("config_delete")
    async def handle_deleted_config(self, guild_id: int):
        self.starboards.pop(guild_id, None)

    # /Sect: Event Handling
    # Sect: Commands

    async def addon_interaction_check(
        self, interaction: discord.Interaction
    ) -> bool:
        return is_valid_starboard_env(interaction)

    @singleton
    class StarboardSettings(app_commands.Group, name="settings"):
        """Commands for managing your starboard"""

        addon: StarboardAddon

        @app_commands.command(name="list")
        @app_commands.checks.has_permissions(manage_channels=True)
        async def starboard_list(self, interaction: discord.Interaction):
            """Lists starboard settings"""
            # Guaranteed by the global check
            assert interaction.guild

            starboard = self.addon.starboards[interaction.guild.id]
            embeds = []

            for setting, setting_info in SETTINGS_MAPPING.items():
                description = (setting_info["description"] or "").format(
                    getattr(starboard, setting)
                )
                embed = (
                    fuchsia.Embed(
                        title=setting_info.display_name,
                        description=description,
                    )
                    .set_thumbnail(url=interaction.guild.icon)
                    .set_author(
                        name=f"Starboard settings for {interaction.guild}",
                    )
                )
                embeds.append(embed)

            menu = ButtonsMenu.from_embeds(embeds)
            menu.add_item(
                ChangeSettingButton(
                    addon=self.addon,
                    label="Change this setting",
                    style=discord.ButtonStyle.primary,
                    row=0,
                )
            )

            await menu.start(interaction)

        @add_setting_autocomplete(
            SETTINGS_MAPPING, setting_param="setting", value_param="new_value"
        )
        @app_commands.command(name="set")
        @app_commands.checks.has_permissions(manage_channels=True)
        @app_commands.describe(
            setting="The setting to set. More information can be found in the settings list",
            new_value="The new value to assign to this setting. More information"
            " can be found in the settings list",
        )
        @app_commands.rename(new_value="new-value")
        async def starboard_set(
            self, interaction: discord.Interaction, setting: str, new_value: str
        ):
            """
            Updates the value of a starboard setting

            More information on the available settings and their functions[JOIN]
            is in the `starboard` command
            """
            await self.addon.set_option(interaction, setting, new_value)
            await interaction.response.send_message(
                f"Setting {SETTINGS_MAPPING[setting].display_name} has been updated!"
            )

    async def set_option(
        self, interaction: discord.Interaction, setting: str, new_value: str
    ):
        assert interaction.guild

        value = await convert_setting(
            interaction, SETTINGS_MAPPING, setting, new_value
        )
        starboard = self.starboards[interaction.guild.id]
        setattr(starboard, setting, value)

        if setting == "emoji":
            value = str(value)
        await self.bot.db.execute(
            f"""
            UPDATE starboards
            SET
                {setting}=$1
            WHERE
                guild_id=$2
            """,
            getattr(value, "id", value),
            interaction.guild.id,
        )
        # ^ Using string formatting in SQL is safe here because
        # the setting is thoroughly validated
        if setting in ["channel", "emoji"]:
            await self.bot.db.execute(
                "DELETE FROM stars WHERE guild_id=$1", interaction.guild.id
            )
            starboard.cached_stars.clear()

    @app_commands.command(name="ignore")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(
        channel="The channel to ignore, can be a channel mention or ID",
        message="The message to ignore, can be a message link or ID",
    )
    async def starboard_ignore(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        message: Optional[str] = None,
    ):
        """
        Ignores a channel or message

        Messages from the channel/the message are prevented from being[JOIN]
        sent to starboard

        Note: If an already starred message is ignored, the star will[JOIN]
        be deleted, *and* the message will be ignored
        """
        assert (
            interaction.guild
            and isinstance(interaction.channel, discord.abc.Messageable)
            and not isinstance(interaction.channel, discord.GroupChannel)
        )

        message_obj = None
        if message:
            parsed_id = parse_id(message)
            message_obj = interaction.channel.get_partial_message(parsed_id)

        if not any(
            [
                isinstance(channel, discord.TextChannel),
                isinstance(message_obj, discord.PartialMessage),
            ]
        ):
            raise TypeError(
                "You must provide at least one valid argument to ignore."
            )

        starboard = self.starboards[interaction.guild.id]

        for snowflake in filter(None, [channel, message_obj]):
            id = snowflake.id

            starboard.ignored.add(id)
            await self.bot.db.execute(
                """
                UPDATE starboards
                SET
                    ignored=array_append(ignored, $1)
                WHERE
                    guild_id=$2
                """,
                id,
                interaction.guild.id,
            )

            if isinstance(
                snowflake, discord.PartialMessage
            ) and await starboard.exists(id):
                await starboard.delete_star(id)

        await interaction.response.send_message(
            "Successfully ignored the provided entity!"
        )

    @app_commands.command(name="unignore")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(
        id="A generic ID to unignore",
        channel="The channel to unignore, can be a channel mention or ID",
        message="The message to unignore, can be a message link or ID",
    )
    async def starboard_unignore(
        self,
        interaction: discord.Interaction,
        id: Optional[str] = None,
        channel: Optional[discord.TextChannel] = None,
        message: Optional[str] = None,
    ):
        """Unignores a channel or message"""
        assert (
            interaction.guild
            and isinstance(interaction.channel, discord.abc.Messageable)
            and not isinstance(interaction.channel, discord.GroupChannel)
        )

        message_obj = None
        if message:
            parsed_id = parse_id(message)
            message_obj = interaction.channel.get_partial_message(parsed_id)

        id = id or ""
        if not any(
            [
                id.isdigit(),
                isinstance(channel, discord.TextChannel),
                isinstance(message_obj, discord.PartialMessage),
            ]
        ):
            raise TypeError(
                "You must provide at least one valid argument to unignore."
            )

        starboard = self.starboards[interaction.guild.id]
        target_id = int(id) if id.isdigit() else None

        for obj in filter(None, [target_id, channel, message_obj]):
            object_id = (
                obj.id if isinstance(obj, discord.abc.Snowflake) else obj
            )

            starboard.ignored.discard(object_id)
            await self.bot.db.execute(
                """
                UPDATE starboards
                SET
                    ignored=array_remove(ignored, $1)
                WHERE
                    guild_id=$2
                """,
                object_id,
                interaction.guild.id,
            )

        await interaction.response.send_message(
            "Successfully unignored the provided entity!"
        )

    @app_commands.command(name="ignored")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def starboard_ignored(self, interaction: discord.Interaction):
        """Displays a list of all ignored items"""
        assert interaction.guild

        starboard = self.starboards[interaction.guild.id]

        formatted: list[str] = []
        for id in starboard.ignored:
            if isinstance(
                channel := self.bot.get_channel(id), discord.abc.GuildChannel
            ):
                formatted.insert(0, f"**Channel** {channel.mention}")
            else:
                formatted.append(f"**Message ID** `{id}`")

        menu = ButtonsMenu.from_iterable(
            formatted or ["No ignored items"],
            per_page=10,
            use_embed=True,
            template_embed=fuchsia.Embed().set_author(
                name=f"Ignored from starboard for {interaction.guild}",
                icon_url=interaction.guild.icon,
            ),
        )
        await menu.start(interaction)

    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def force_star_ctx(
        self, interaction: discord.Interaction, message: discord.Message
    ):
        """
        Sends a message directly to the starboard, regardless of reactions

        If the message has already been force-starred, then this unstars it.

        Messages that are already on the starboard cannot be force-starred.
        """
        assert interaction.guild
        if is_valid_starboard_env(interaction):
            pass

        starboard = self.starboards[interaction.guild.id]
        if starboard.channel is None:
            raise RuntimeError("This server hasn't set its starboard channel")

        star = await starboard.get_star(
            message.id,
            from_starboard_message=(
                interaction.channel_id == starboard.channel.id
            ),
        )
        # ignore natural stars
        if star is not None and star.forced is False:
            await interaction.response.send_message(
                "Cannot force-star an already-starred message", ephemeral=True
            )
            return

        if star is None:
            star = await starboard.create_star(
                await message.fetch(), 0, forced=True
            )
        elif star is not None and star.forced is True:
            await starboard.delete_star(star.message_id)

        await interaction.response.send_message(
            "Toggled force-star status", ephemeral=True
        )


async def setup(bot: fuchsia.Fuchsia):
    await bot.add_cog(StarboardAddon(bot))

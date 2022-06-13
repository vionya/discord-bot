# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

import discord
import neo
from discord import app_commands
from neo.classes.containers import TimedCache
from neo.classes.transformers import max_days_converter, text_channel_transformer
from neo.modules import ButtonsMenu
from neo.tools import convert_setting, instantiate, shorten
from neo.tools.checks import valid_starboard_env

from .auxiliary.starboard import ChangeSettingButton

if TYPE_CHECKING:
    from asyncpg import Pool
    from neo.types.settings_mapping import SettingsMapping

SETTINGS_MAPPING: SettingsMapping = {
    "channel": {"transformer": text_channel_transformer, "description": None},
    "threshold": {"transformer": int, "description": None},
    "format": {"transformer": str, "description": None},
    "max_days": {"transformer": max_days_converter, "description": None},
    "emoji": {"transformer": discord.PartialEmoji.from_str, "description": None},
}


class Star:
    __slots__ = ("message_id", "starboard_message", "stars")

    def __init__(
        self, *, message_id: int, starboard_message: discord.PartialMessage, stars: int
    ):
        self.message_id = message_id
        self.starboard_message = starboard_message
        self.stars = stars

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
        stars: list,
        threshold: int,
        format: str,
        max_days: int,
        emoji: discord.PartialEmoji,
        ignored: set[int],
        pool: Pool,
    ):
        self.channel = channel
        self.threshold = threshold
        self.format = format
        self.max_days = max_days
        self.emoji = emoji
        self.ignored = ignored
        self.star_ids = [star["message_id"] for star in stars]

        # Use timed cache so that stars are not persisting for
        # longer than they reasonably should be
        self.cached_stars = TimedCache(300)
        self.lock = asyncio.Lock()
        self.pool = pool

    async def get_star(self, id: int) -> Star | None:
        if not self.channel:
            return None

        if id in self.cached_stars:
            return self.cached_stars[id]

        star_data = await self.pool.fetchrow(
            "SELECT * FROM stars WHERE message_id=$1", id
        )

        if star_data:
            starboard_msg = self.channel.get_partial_message(
                star_data["starboard_message_id"]
            )
            star = Star(
                message_id=id, starboard_message=starboard_msg, stars=star_data["stars"]
            )
            self.cached_stars[id] = star
            return star
        return None

    async def create_star(self, message: discord.Message, stars: int):
        if (
            not message.guild
            or not self.channel
            or any([message.id in self.star_ids, self.lock.locked()])
        ):
            return

        async with self.lock:
            embed = neo.Embed(description="").set_author(
                name=message.author, icon_url=message.author.display_avatar
            )

            if message.content:
                embed.description = shorten(message.content, 1900) + "\n\n"

            if message.stickers:
                embed.add_field(
                    name=f"Stickers [x{len(message.stickers)}]",
                    value="\n".join(
                        f"`{sticker.name}`" for sticker in message.stickers
                    ),
                    inline=False,
                )

            if attachments := (*message.attachments, *message.embeds):
                if not embed.image:
                    embed.set_image(url=attachments[0].url)
                embed.add_field(
                    name=f"Attachments/Embeds [x{len(attachments)}]",
                    value="\n".join(
                        "[{0}]({1})".format(
                            discord.utils.escape_markdown(
                                getattr(attachment, "filename", "Embed")
                            ),
                            attachment.url,
                        )
                        for attachment in attachments
                    ),
                    inline=False,
                )

            view = discord.ui.View(timeout=0)
            view.add_item(
                discord.ui.Button(url=message.jump_url, label="Jump to original")
            )

            starboard_message = await self.channel.send(
                self.format.format(stars=stars), embed=embed, view=view
            )
            star = Star(
                message_id=message.id, stars=stars, starboard_message=starboard_message
            )

            await self.pool.execute(
                """
                INSERT INTO stars (
                    guild_id,
                    message_id,
                    channel_id,
                    stars,
                    starboard_message_id
                ) VALUES (
                    $1, $2, $3, $4, $5
                )
                """,
                message.guild.id,
                message.id,
                message.channel.id,
                stars,
                star.starboard_message.id,
            )

            self.star_ids.append(message.id)
            self.cached_stars[message.id] = star
            return star

    async def delete_star(self, id: int):
        star = await self.get_star(id)
        if star:
            await star.starboard_message.delete()

        await self.pool.execute("DELETE FROM stars WHERE message_id=$1", id)
        del self.cached_stars[id]
        self.star_ids.remove(id)
        return star

    async def edit_star(self, id: int, stars: int):
        star = await self.get_star(id)
        if not star:
            return await self.delete_star(id)

        star.stars = stars

        try:
            await star.edit(content=self.format.format(stars=star.stars))
        except discord.NotFound:  # Delete star from records if its message has been deleted
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


@app_commands.guild_only()
class StarboardAddon(
    neo.Addon,
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

    def __init__(self, bot: neo.Neo):
        self.bot = bot
        self.ready = False
        self.starboards: dict[int, Starboard] = {}

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
            self.starboards[guild_id] = await self.create_starboard(guild_id, settings)
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
        star_records = await self.bot.db.fetch(
            """
            SELECT message_id
            FROM stars
            WHERE guild_id=$1
            """,
            guild_id,
        )

        channel = self.bot.get_channel(starboard_settings["channel"])

        return Starboard(
            channel=channel,  # type: ignore
            stars=star_records,
            threshold=starboard_settings["threshold"],
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

    @neo.Addon.listener("on_raw_reaction_add")
    @neo.Addon.listener("on_raw_reaction_remove")
    async def handle_individual_reaction(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id not in self.starboards or not payload.guild_id:
            return
        starboard = self.starboards[payload.guild_id]

        if not self.predicate(starboard, payload):
            return

        if payload.message_id not in starboard.star_ids:
            if (
                datetime.now(timezone.utc)
                - discord.Object(payload.message_id).created_at
            ).days > starboard.max_days:
                return

            channel = self.bot.get_channel(payload.channel_id)
            if not isinstance(channel, discord.TextChannel):
                return
            message = await channel.fetch_message(payload.message_id)

            reaction_count = getattr(
                next(
                    filter(
                        lambda r: self.reaction_check(starboard, r.emoji),
                        message.reactions,
                    ),
                    None,
                ),
                "count",
                0,
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
            if not star:
                return

            match payload.event_type:
                case "REACTION_ADD":
                    star.stars += 1
                case "REACTION_REMOVE":
                    star.stars -= 1

            if star.stars < starboard.threshold:
                await starboard.delete_star(star.message_id)
            else:
                await starboard.edit_star(star.message_id, star.stars)

    @neo.Addon.listener("on_raw_reaction_clear")
    @neo.Addon.listener("on_raw_reaction_clear_emoji")
    @neo.Addon.listener("on_raw_message_delete")
    async def handle_terminations(self, payload):
        if payload.guild_id not in self.starboards or not payload.guild_id:
            return
        starboard = self.starboards[payload.guild_id]

        if not self.predicate(starboard, payload):
            return

        if isinstance(payload, discord.RawReactionClearEmojiEvent):
            if not self.reaction_check(starboard, payload.emoji):
                return

        if payload.message_id in starboard.star_ids:
            await starboard.delete_star(payload.message_id)

    @neo.Addon.listener("on_guild_channel_delete")
    async def handle_starboard_channel_delete(self, channel: discord.abc.GuildChannel):
        if channel.guild.id not in self.starboards:
            return

        starboard = self.starboards[channel.guild.id]
        if channel.id == getattr(starboard.channel, "id", None):
            await self.bot.db.execute(
                "DELETE FROM stars WHERE guild_id=$1", channel.guild.id
            )
            starboard.cached_stars.clear()
        starboard.channel = None

    @neo.Addon.recv("config_update")
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

    @neo.Addon.recv("config_delete")
    async def handle_deleted_config(self, guild_id: int):
        self.starboards.pop(guild_id, None)

    # /Sect: Event Handling
    # Sect: Commands

    @instantiate
    class StarboardSettings(app_commands.Group, name="settings"):
        """Commands for managing your starboard"""

        addon: StarboardAddon

        @app_commands.command(name="list")
        @app_commands.checks.has_permissions(manage_channels=True)
        @valid_starboard_env()
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
                embed = neo.Embed(
                    title=f"Starboard settings for {interaction.guild}",
                    description=f"**Setting: `{setting}`**\n\n" + description,
                ).set_thumbnail(url=interaction.guild.icon)
                embeds.append(embed)

            menu = ButtonsMenu.from_embeds(embeds)
            menu.add_item(
                ChangeSettingButton(
                    addon=self.addon,
                    settings=SETTINGS_MAPPING,
                    label="Change this setting",
                    style=discord.ButtonStyle.primary,
                    row=0,
                )
            )

            await menu.start(interaction)

        @app_commands.command(name="set")
        @app_commands.checks.has_permissions(manage_channels=True)
        @app_commands.describe(
            setting="The setting to set. More information can be found in the settings list",
            new_value="The new value to assign to this setting. More information"
            " can be found in the settings list",
        )
        @app_commands.rename(new_value="new-value")
        @valid_starboard_env()
        async def starboard_set(
            self, interaction: discord.Interaction, setting: str, new_value: str
        ):
            """
            Updates the value of a starboard setting

            More information on the available settings and their functions is in the `starboard` command
            """
            await self.addon.set_option(interaction, setting, new_value)
            await interaction.response.send_message(
                f"Setting `{setting}` has been changed!"
            )

        @starboard_set.autocomplete("setting")
        async def starboard_set_autocomplete(
            self, interaction: discord.Interaction, current: str
        ):
            return [
                *map(
                    lambda k: discord.app_commands.Choice(name=k, value=k),
                    filter(lambda k: current in k, SETTINGS_MAPPING.keys()),
                )
            ]

    async def set_option(
        self, interaction: discord.Interaction, setting: str, new_value: str
    ):
        assert interaction.guild

        value = await convert_setting(interaction, SETTINGS_MAPPING, setting, new_value)
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
        message="The message to ignore, must be a message ID",
    )
    @valid_starboard_env()
    async def starboard_ignore(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        message: Optional[str] = None,
    ):
        """
        Ignores a channel or message

        Messages from the channel/the message are prevented
        from being sent to starboard

        Note: If an already starred message is ignored, the
        star will be deleted, *and* the message will be ignored
        """
        assert interaction.guild and isinstance(
            interaction.channel, discord.abc.Messageable
        )

        message_obj = None
        if message and message.isdigit():
            message_obj = interaction.channel.get_partial_message(int(message))
        elif message and not message.isdigit():
            raise TypeError("`message` must be a message ID")

        if not any(
            [
                isinstance(channel, discord.TextChannel),
                isinstance(message_obj, discord.PartialMessage),
            ]
        ):
            raise TypeError("You must provide at least one valid argument to ignore.")

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

            if (
                isinstance(snowflake, discord.PartialMessage)
                and id in starboard.star_ids
            ):
                await starboard.delete_star(id)

        await interaction.response.send_message(
            "Successfully ignored the provided entity!"
        )

    @app_commands.command(name="unignore")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(
        id="A generic ID to unignore",
        channel="The channel to unignore, can be a channel mention or ID",
        message="The message to unignore, must be a message ID",
    )
    @valid_starboard_env()
    async def starboard_unignore(
        self,
        interaction: discord.Interaction,
        id: Optional[str] = None,
        channel: Optional[discord.TextChannel] = None,
        message: Optional[str] = None,
    ):
        """Unignores a channel or message"""
        assert interaction.guild and isinstance(
            interaction.channel, discord.abc.Messageable
        )

        message_obj = None
        if message and message.isdigit():
            message_obj = interaction.channel.get_partial_message(int(message))
        elif message and not message.isdigit():
            raise TypeError("`message` must be a message ID")

        id = id or ""
        if not any(
            [
                id.isdigit(),
                isinstance(channel, discord.TextChannel),
                isinstance(message_obj, discord.PartialMessage),
            ]
        ):
            raise TypeError("You must provide at least one valid argument to unignore.")

        starboard = self.starboards[interaction.guild.id]
        target_id = int(id) if id.isdigit() else None

        for obj in filter(None, [target_id, channel, message_obj]):
            object_id = obj.id if isinstance(obj, discord.abc.Snowflake) else obj

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
    @valid_starboard_env()
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
            template_embed=neo.Embed().set_author(
                name=f"Ignored from starboard for {interaction.guild}",
                icon_url=interaction.guild.icon,
            ),
        )
        await menu.start(interaction)


async def setup(bot: neo.Neo):
    await bot.add_cog(StarboardAddon(bot))

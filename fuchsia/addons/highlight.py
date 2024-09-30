# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 sardonicism-04
from __future__ import annotations

import asyncio
import re
from bisect import insort
from collections import defaultdict
from enum import Enum
from functools import cached_property
from operator import attrgetter
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands

import fuchsia
from fuchsia.classes.containers import TimedSet
from fuchsia.classes.partials import PartialUser
from fuchsia.classes.timer import periodic
from fuchsia.modules import ButtonsMenu
from fuchsia.tools import (
    generate_autocomplete_list,
    is_clear_all,
    is_valid_index,
    send_confirmation,
    shorten,
)
from fuchsia.tools.checks import is_registered_profile_predicate

if TYPE_CHECKING:
    from fuchsia.classes.containers import FuchsiaUser


class DefaultAvatars(Enum):
    Blurple = "<:_:863449882088833065>"
    Grey = "<:_:863449883121418320>"
    Green = "<:_:863449884157280307>"
    Orange = "<:_:863449885088808970>"
    Red = "<:_:863449885834739712>"
    Pink = "<:_:863449887403147314>"


MAX_TRIGGERS = 100
CUSTOM_EMOJI = re.compile(r"<a?:[a-zA-Z0-9_]{2,}:\d+>")


def format_hl_context(message: discord.Message, is_trigger=False):
    fmt = (
        "**{0} [{1.author.display_name}]({1.jump_url})** {1.content}"
        if is_trigger
        else "{0} **{1.author.display_name}** {1.content}"
    )
    # strip markdown and replace custom emoji
    message.content = CUSTOM_EMOJI.sub(
        "❔", discord.utils.escape_markdown(message.content)
    )
    if message.attachments:
        message.content += " *[Attachment x{}]*".format(
            len(message.attachments)
        )
    if message.embeds:
        message.content += " *[Embed x{}]*".format(len(message.embeds))
    if message.stickers:
        message.content += " *[Sticker x{}]*".format(len(message.stickers))

    match int(message.author.default_avatar.key):
        case 1:
            enum_member = DefaultAvatars.Grey
        case 2:
            enum_member = DefaultAvatars.Green
        case 3:
            enum_member = DefaultAvatars.Orange
        case 4:
            enum_member = DefaultAvatars.Red
        case 5:
            enum_member = DefaultAvatars.Pink
        case _:
            enum_member = DefaultAvatars.Blurple

    return fmt.format(enum_member.value, message)


class Highlight:
    # Max number of characters in a trigger
    MAX_LEN = 100

    __slots__ = ("bot", "content", "user_id", "pattern")

    def __init__(self, bot: fuchsia.Fuchsia, *, content: str, user_id: int):
        self.bot = bot
        self.content = content
        self.user_id = user_id
        self.pattern = re.compile(rf"\b{self.content}\b", re.I)

    def __repr__(self):
        return (
            "<{0.__class__.__name__} user_id={0.user_id!r} "
            "content={0.content!r}>"
        ).format(self)

    async def predicate(self, message: discord.Message) -> bool:
        # The bot and the highlight user cannot trigger a highlight
        if any([message.author.id == self.user_id, message.author.bot]):
            return False

        # Don't highlight users who have disabled highlight receipt
        if self.bot.profiles[self.user_id].receive_highlights is False:
            return False

        # If any of the following IDs:
        # - message
        # - guild
        # - channel
        # - author
        # are in the user's ignored list, fail the check
        blacklist = self.bot.profiles[self.user_id].hl_blocks
        if any(
            attrgetter(attr)(message) in blacklist
            for attr in ("id", "guild.id", "channel.id", "author.id")
        ):
            return False

        # Don't highlight users with messages they are mentioned in
        if self.user_id in [m.id for m in message.mentions]:
            return False

        # This lets us update the channel members and make sure the user exists
        try:
            member = await message.guild.fetch_member(self.user_id, cache=True)  # type: ignore
        except discord.NotFound:
            return False

        members: list[discord.Member] = []
        channel = message.channel

        match channel:
            # Threads with a forum channel parent
            # Currently untested since they're inaccessible for testing
            case discord.Thread(parent=discord.ForumChannel()):
                if channel.parent.permissions_for(member).read_messages:  # type: ignore
                    members = [member]

            # Threads with a text channel parent
            case discord.Thread(parent=discord.TextChannel()):
                # In private channel, see if we can fetch the member from the thread
                # If yes, deliver highlight
                if channel.is_private():
                    try:
                        await channel.fetch_member(self.user_id)
                        members = [member]
                    except discord.NotFound:
                        # If the member isn't found, the members list remains empty
                        # The check fails
                        pass

                # Otherwise it's a public thread so we can just pull from the
                # parent channel's members
                else:
                    members = channel.parent.members  # type: ignore

            # Same logic as above applies to text channels
            case discord.TextChannel():
                members = channel.members

            # Since voice channel members aren't the same as text channel,
            # we have to run a permissions check to see if the member
            # can connect to the voice channel
            case discord.VoiceChannel():
                if channel.permissions_for(member).connect:
                    members = [member]

            # In any other case, do nothing
            # This leaves the members list empty, so the check fails
            case _:
                pass

        if member not in members:  # Check channel membership
            return False

        return True

    async def to_send_kwargs(
        self, message: discord.Message, later_triggers: set[discord.Message]
    ):
        content = ""
        triggers: set[discord.Message] = {message, *later_triggers}
        async for m in message.channel.history(limit=6, around=message):
            if len(content + m.content) > 1500:  # Don't exceed embed limits
                m.content = "*[Omitted due to length]*"
            formatted = format_hl_context(m, m in triggers)
            content = f"{formatted}\n{content}"

        embed = fuchsia.Embed(
            title="In {0.guild.name}/#{0.channel.name}".format(message),
            description=content,
        )

        view = discord.ui.View(timeout=0)
        view.add_item(
            discord.ui.Button(url=message.jump_url, label="Jump to message")
        )

        return {
            "content": "{0}: {1}".format(
                message.author, shorten(message.content, 75)
            ),
            "embed": embed,
            "view": view,
            "silent": self.bot.profiles[self.user_id].silence_hl,
        }

    def matches(self, other: str):
        return self.pattern.search(other)


QueuedHighlightsType = defaultdict[
    int, dict[int, tuple[Highlight, discord.Message, set[discord.Message]]]
]


class Highlights(fuchsia.Addon, app_group=True, group_name="highlight"):
    """Commands for managing highlights"""

    def __init__(self, bot: fuchsia.Fuchsia):
        self.bot = bot
        self.highlights: defaultdict[int, list[Highlight]] = defaultdict(list)
        self.grace_periods: dict[int, TimedSet[int]] = {}
        self.queued_highlights: QueuedHighlightsType = defaultdict(dict)
        asyncio.create_task(self.__ainit__())

    async def __ainit__(self):
        await self.bot.wait_until_ready()

        # fetch reminders ordered by content
        for record in await self.bot.db.fetch(
            "SELECT * FROM highlights ORDER BY content ASC"
        ):
            self.highlights[record["user_id"]].append(
                Highlight(self.bot, **record)
            )

        for profile in self.bot.profiles.values():
            self.grace_periods[profile.user_id] = TimedSet(
                timeout=profile.hl_timeout * 60
            )

        self.send_queued_highlights.start()

    def cog_unload(self):
        self.send_queued_highlights.shutdown()

    @cached_property  # Cache to avoid being re-computed after every message
    def flat_highlights(self):
        return [hl for hl_list in self.highlights.values() for hl in hl_list]

    def recompute_flattened(self):
        if hasattr(self, "flat_highlights"):
            del self.flat_highlights
        self.flat_highlights

    @fuchsia.Addon.listener("on_message")
    async def listen_for_highlights(self, message: discord.Message):
        if not self.bot.is_ready():
            return  # Return if bot is not ready, so flat_highlights is computed correctly

        # DMs may never trigger highlights
        if message.guild is None:
            return

        # If the server has disallowed highlights, then quit processing
        if message.guild.id in self.bot.configs:
            guild_config = self.bot.configs[message.guild.id]
            if guild_config.allow_highlights is False:
                return

        # If the message was sent by someone with highlights, add the
        # current channel ID to the set of grace periods
        if message.author.id in {hl.user_id for hl in self.flat_highlights}:
            self.grace_periods[message.author.id].add(message.channel.id)

        # Loop over every highlight that matches the message content
        for hl in filter(
            lambda hl: hl.matches(message.content), self.flat_highlights
        ):
            # If the channel is in a grace period, ignore
            if message.channel.id in self.grace_periods[hl.user_id]:
                continue
            # If the highlight's predicate fails, ignore
            if not await hl.predicate(message):
                continue
            channel_queue = self.queued_highlights[message.channel.id]
            # If the user has no highlights queued for the message's channel,
            # set their value in the channel to a tuple of the relevant data
            if hl.user_id not in self.queued_highlights[message.channel.id]:
                channel_queue[hl.user_id] = (hl, message, set())
            # If they *are* in the queue, add the message as a "context"
            # message in the tuple's extras set
            else:
                channel_queue[hl.user_id][2].add(message)

    @periodic(5)
    async def send_queued_highlights(self):
        queue = self.queued_highlights.copy()
        self.queued_highlights.clear()
        for hl, message, later_triggers in [
            pair for nested in queue.values() for pair in nested.values()
        ]:
            try:
                await self.bot.get_user(hl.user_id, as_partial=True).send(
                    **await hl.to_send_kwargs(message, later_triggers)
                )
            except discord.Forbidden:
                # If a highlight delivery results in a Forbidden response,
                # then disable highlight receipt for that profile to avoid
                # wasting future API calls
                self.bot.profiles[hl.user_id].receive_highlights = False

    @fuchsia.Addon.recv("user_settings_update")
    async def handle_update_profile(self, user_id: int, profile: FuchsiaUser):
        if self.grace_periods.get(user_id):
            current_timeout = self.grace_periods[user_id].timeout
            if (profile.hl_timeout * 60) == current_timeout:
                return
            self.grace_periods.pop(user_id).clear()

        self.grace_periods[profile.user_id] = TimedSet(
            timeout=profile.hl_timeout * 60
        )

    # Need to dynamically account for deleted profiles
    @fuchsia.Addon.recv("profile_delete")
    async def handle_deleted_profile(self, user_id: int):
        if (popped := self.grace_periods.pop(user_id, None)) is not None:
            popped.clear()  # Cleanup TimedSet
        self.highlights.pop(user_id, None)
        self.recompute_flattened()

    async def addon_interaction_check(
        self, interaction: discord.Interaction
    ) -> bool:
        return await is_registered_profile_predicate(interaction)

    @app_commands.command(name="list")
    async def highlight_list(self, interaction: discord.Interaction):
        """List your highlights"""
        user_highlights = self.highlights.get(interaction.user.id, [])
        formatted_hls = []

        # sort highlights alphabetically
        for hl in sorted(user_highlights, key=lambda h: h.content):
            formatted_hls.append(f"- `{hl.content}`")

        menu = ButtonsMenu.from_iterable(
            formatted_hls or ["No highlights"],
            per_page=10,
            use_embed=True,
            template_embed=fuchsia.Embed()
            .set_author(
                name=f"{interaction.user}'s highlights",
                icon_url=interaction.user.display_avatar,
            )
            .set_footer(
                text=f"{len(user_highlights)}/{MAX_TRIGGERS} slots used"
            ),
        )
        await menu.start(interaction)

    @app_commands.command(name="add")
    @app_commands.describe(content="The word or phrase to be highlighted by")
    async def highlight_add(
        self,
        interaction: discord.Interaction,
        content: app_commands.Range[str, 1, Highlight.MAX_LEN],
    ):
        """
        Add a new highlight

        Highlights will notify you when the word/phrase you add is said in chat.

        ### Notes
        - Highlights will **never** be triggered from private threads that[JOIN]
        you are not a member of
        - Highlights will **never** be triggered by bots
        - You must be a member of a channel to be highlighted in it
        """
        if len(self.highlights.get(interaction.user.id, [])) >= MAX_TRIGGERS:
            raise ValueError("You've used up all of your highlight slots!")

        if content in [
            hl.content for hl in self.highlights.get(interaction.user.id, [])
        ]:
            raise ValueError(
                "Cannot have multiple highlights with the same content."
            )

        result = await self.bot.db.fetchrow(
            """
            INSERT INTO highlights (
                user_id,
                content
            ) VALUES ( $1, $2 )
            RETURNING *
            """,
            interaction.user.id,
            content,
        )
        # use bisect insort to maintain ordering
        insort(
            self.highlights[interaction.user.id],
            Highlight(self.bot, **result),
            key=lambda h: h.content,
        )
        self.recompute_flattened()
        await send_confirmation(
            interaction, predicate=f"added `{content}` as a new highlight"
        )

    @app_commands.command(name="remove")
    @app_commands.rename(index="highlight")
    @app_commands.describe(index="A highlight to remove")
    async def highlight_remove(
        self, interaction: discord.Interaction, index: str
    ):
        """Remove a highlight"""
        if is_clear_all(index):
            highlights = self.highlights.get(interaction.user.id, []).copy()
            self.highlights.pop(interaction.user.id, None)

        elif is_valid_index(index):
            try:
                highlights = [
                    self.highlights[interaction.user.id].pop(int(index) - 1)
                ]
            except IndexError:
                raise IndexError(
                    "One or more of the provided indices is invalid."
                )

        else:
            raise TypeError("Invalid input provided.")

        await self.bot.db.execute(
            """
            DELETE FROM
                highlights
            WHERE
                user_id = $1 AND
                content = ANY($2::TEXT[])
            """,
            interaction.user.id,
            [*map(attrgetter("content"), highlights)],
        )
        self.recompute_flattened()
        await send_confirmation(interaction, predicate="removed highlight(s)")

    @highlight_remove.autocomplete("index")
    async def highlight_remove_autocomplete(
        self, interaction: discord.Interaction, current
    ):
        if interaction.user.id not in self.bot.profiles:
            return []

        highlights = [
            highlight.content
            for highlight in self.highlights[interaction.user.id]
        ]
        return generate_autocomplete_list(
            highlights, current, insert_wildcard=True
        )

    def perform_blocklist_action(
        self, *, profile: FuchsiaUser, ids: list[int], action="block"
    ):
        blacklist = {
            *profile.hl_blocks,
        }
        ids_set = {
            *ids,
        }

        if action == "unblock":
            blacklist -= ids_set
        else:
            blacklist |= ids_set

        profile.hl_blocks = [*blacklist]

    @app_commands.command(name="block")
    @app_commands.describe(
        id="The ID of a user, server, or channel to block",
        user="A user to block",
        channel="A channel to block",
    )
    async def highlight_block(
        self,
        interaction: discord.Interaction,
        id: Optional[str] = None,
        user: Optional[discord.User | discord.Member] = None,
        channel: Optional[discord.TextChannel] = None,
    ):
        """Block a target from highlighting you"""
        if not (id or "").isnumeric() and not any([user, channel]):
            raise TypeError("Please input a valid ID.")

        profile = self.bot.profiles[interaction.user.id]

        ids = [
            *map(
                lambda obj: obj.id
                if isinstance(obj, discord.abc.Snowflake)
                else int(obj),
                filter(None, [user, channel, id]),
            )
        ]

        self.perform_blocklist_action(profile=profile, ids=ids)
        await send_confirmation(interaction, predicate="updated your blocklist")

    @app_commands.command(name="blocklist")
    async def highlight_block_list(self, interaction: discord.Interaction):
        """
        Manage a blocklist for highlights.
        """
        profile = self.bot.profiles[interaction.user.id]

        def transform_mention(id):
            mention = getattr(
                self.bot.get_guild(id),
                "name",
                getattr(self.bot.get_channel(id), "mention", f"<@{id}>"),
            )  # Yes, this could lead to fake user mentions
            return "`{0}` [{1}]".format(id, mention)

        menu = ButtonsMenu.from_iterable(
            [*map(transform_mention, profile.hl_blocks)]
            or ["No highlight blocks"],
            per_page=10,
            use_embed=True,
            template_embed=fuchsia.Embed().set_author(
                name=f"{interaction.user}'s highlight blocks",
                icon_url=interaction.user.display_avatar,
            ),
        )
        await menu.start(interaction)

    @app_commands.command(name="unblock")
    @app_commands.describe(
        id="The ID of a user, server, or channel to unblock",
        user="A user to unblock",
        channel="A channel to unblock",
    )
    async def highlight_unblock(
        self,
        interaction: discord.Interaction,
        id: Optional[str] = None,
        user: Optional[discord.User | discord.Member] = None,
        channel: Optional[discord.TextChannel] = None,
    ):
        """
        Unblock entities from triggering your highlights

        Servers, users, and channels can all be unblocked via ID

        One *or more* IDs can be provided to this command
        """
        if not (id or "").isnumeric() and not any([user, channel]):
            raise TypeError("Please input a valid ID.")

        profile = self.bot.profiles[interaction.user.id]

        ids = [
            *map(
                lambda obj: obj.id
                if isinstance(obj, discord.abc.Snowflake)
                else int(obj),
                filter(None, [user, channel, id]),
            )
        ]

        self.perform_blocklist_action(
            profile=profile, ids=ids, action="unblock"
        )
        await send_confirmation(interaction, predicate="updated your blocklist")

    @highlight_unblock.autocomplete("id")
    async def highlight_unblock_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        profile = self.bot.profiles[interaction.user.id]

        def transform_mention(id):
            mention: Optional[
                discord.Guild
                | discord.TextChannel
                | PartialUser
                | discord.User
                | str
            ] = getattr(
                self.bot.get_guild(id),
                "name",
                getattr(
                    self.bot.get_channel(id),
                    "name",
                    getattr(self.bot.get_user(id), "name"),
                ),
            )

            return "{0} [{1}]".format(id, mention or "Unknown")

        return [
            discord.app_commands.Choice(
                name=transform_mention(_id), value=str(_id)
            )
            for _id in filter(
                lambda block: current in block, map(str, profile.hl_blocks)
            )
        ][:25]


async def setup(bot: fuchsia.Fuchsia):
    await bot.add_cog(Highlights(bot))

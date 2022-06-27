# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import discord
import neo
from discord import app_commands
from neo.classes.timer import periodic
from neo.modules import ButtonsMenu
from neo.tools import (
    generate_autocomplete_list,
    is_clear_all,
    is_registered_profile,
    is_valid_index,
    send_confirmation,
    shorten,
    try_or_none,
)
from neo.tools.time_parse import TimedeltaWithYears, parse_absolute, parse_relative

MAX_REMINDERS = 15
MAX_REMINDER_LEN = 1000


class Reminder:
    __slots__ = (
        "user_id",
        "reminder_id",
        "content",
        "end_time",
        "bot",
        "_done",
    )

    def __init__(
        self,
        *,
        user_id: int,
        reminder_id: UUID,
        content: str,
        end_time: datetime,
        bot: neo.Neo,
    ):
        self.user_id = user_id
        self.reminder_id = reminder_id
        self.content = content
        self.end_time = end_time
        self.bot = bot
        self._done = False

    async def poll(self, poll_time: datetime):
        if poll_time >= self.end_time:
            await self.deliver()

    async def deliver(self):
        try:
            dest = self.bot.get_user(self.user_id, as_partial=True)
            await dest.send(
                "<@{0}> **Reminder**:\n> {1}".format(self.user_id, self.content),
                allowed_mentions=discord.AllowedMentions(
                    users=[discord.Object(self.user_id)]
                ),
            )
        except discord.HTTPException:
            return

        finally:
            await self.delete()

    async def delete(self):
        """Remove this reminder from the database"""
        self._done = True
        await self.bot.db.execute(
            """
            DELETE FROM
                reminders
            WHERE
                user_id=$1 AND
                reminder_id=$2 AND
                content=$3 AND
                end_time=$4
            """,
            self.user_id,
            self.reminder_id,
            self.content,
            self.end_time,
        )
        self.bot.broadcast("reminder_removed", self.user_id)


class Reminders(neo.Addon, app_group=True, group_name="remind"):
    """Commands for managing reminders"""

    def __init__(self, bot: neo.Neo):
        self.bot = bot
        self.reminders: dict[int, list[Reminder]] = defaultdict(list)
        asyncio.create_task(self.__ainit__())

    async def __ainit__(self):
        await self.bot.wait_until_ready()

        for record in await self.bot.db.fetch("SELECT * FROM reminders"):
            reminder = Reminder(bot=self.bot, **record)
            self.reminders[record["user_id"]].append(reminder)

        self.poll_reminders.start()

    @neo.Addon.recv("profile_delete")
    async def handle_deleted_profile(self, user_id: int):
        for reminder in self.reminders.pop(user_id, []):
            await reminder.delete()

    @neo.Addon.recv("reminder_removed")
    async def handle_removed_reminder(self, user_id: int):
        self.reminders[user_id] = [
            *filter(lambda r: not r._done, self.reminders[user_id].copy())
        ]

    @periodic(1)
    async def poll_reminders(self):
        now = datetime.now(timezone.utc)
        for reminder_list in self.reminders.values():
            for reminder in reminder_list:
                await reminder.poll(now)

    def cog_unload(self):
        self.poll_reminders.shutdown()

    async def add_reminder(
        self,
        *,
        user_id: int,
        reminder_id: UUID,
        content: str,
        end_time: datetime,
    ):
        data = await self.bot.db.fetchrow(
            """
            INSERT INTO reminders (
                user_id,
                reminder_id,
                content,
                end_time
            ) VALUES (
                $1, $2, $3, $4
            ) RETURNING *
            """,
            user_id,
            reminder_id,
            content,
            end_time,
        )
        reminder = Reminder(bot=self.bot, **data)
        self.reminders[user_id].append(reminder)

    @app_commands.command(name="set")
    @app_commands.describe(
        when="When the reminder should be delivered. See this command's help entry for more info",
        content="The content to remind yourself about. Can be empty",
    )
    @is_registered_profile()
    async def reminder_set(
        self, interaction: discord.Interaction, when: str, content: Optional[str] = None
    ):
        """
        Schedule a reminder

        `when` may be either absolute or relative.

        **__Absolute__**
        A select few date/time formats are supported:
        - `month date, year`
        Ex: /remind set `when: Mar 2, 2022` `content: Dance`
        - `hour:minute`
        Ex: /remind set `when: 14:08` `content: Do something obscure`
        - `month date, year at hour:minute`
        Ex: /remind set `when: January 19, 2038 at 3:14` `content: Y2k38`

        All times are required to be in 24-hour format.

        **Note**
        If you have configured a timezone in your neo
        profile, it will be used to localize date/time.
        Otherwise, date/times will be in UTC.

        **__Relative__**
        Offsets have the following requirements:
        - Must be one of `years`, `weeks`, `days`,
        `hours`, `minutes`, and `seconds`
        - Not all time units have to be used
        - Time units have to be ordered by magnitude

        **Examples**
        /remind set `when: 5 years` `content: Hey, hello!`
        /remind set `when: 4h30m` `content: Check what time it is`
        /remind set `when: 3 weeks, 2 days` `content: Do something funny`
        """
        profile = self.bot.profiles[interaction.user.id]
        tz = profile.timezone or timezone.utc

        if len(self.reminders[interaction.user.id]) >= MAX_REMINDERS:
            raise ValueError("You've used up all of your reminder slots!")

        (time_data, remainder) = try_or_none(parse_relative, when) or parse_absolute(
            when, tz=profile.timezone or timezone.utc
        )

        if len(remainder) > MAX_REMINDER_LEN:
            raise ValueError(
                f"Reminders cannot be longer than {MAX_REMINDER_LEN:,} characters!"
            )

        match time_data:
            case TimedeltaWithYears():
                future_time = datetime.now(timezone.utc) + time_data
            case datetime():
                future_time = time_data.replace(tzinfo=tz)
            case _:
                raise RuntimeError("Unknown error in future_time assignment")

        timestamp: int = int(future_time.timestamp())
        await self.add_reminder(
            user_id=interaction.user.id,
            reminder_id=uuid4(),
            content=content or "...",
            end_time=future_time,
        )
        await interaction.response.send_message(
            f"Your reminder will be delivered <t:{timestamp}:R> [<t:{timestamp}>]"
        )

    @app_commands.command(name="list")
    @is_registered_profile()
    async def remind_list(self, interaction: discord.Interaction):
        """Lists your active reminders"""
        reminders = self.reminders[interaction.user.id].copy()
        formatted_reminders: list[str] = []

        for index, reminder in enumerate(reminders, 1):
            formatted_reminders.append(
                "`{0}` {1}\n> Triggers <t:{2}:R>".format(
                    index,
                    shorten(reminder.content, 50),
                    int(reminder.end_time.timestamp()),
                )
            )
        menu = ButtonsMenu.from_iterable(
            formatted_reminders or ["No reminders"],
            per_page=5,
            use_embed=True,
            template_embed=neo.Embed().set_author(
                name=f"{interaction.user}'s reminders",
                icon_url=interaction.user.display_avatar,
            ),
        )
        await menu.start(interaction)

    @app_commands.command(name="view")
    @app_commands.describe(index="A reminder index to view")
    @is_registered_profile()
    async def remind_view(self, interaction: discord.Interaction, index: int):
        """View the full content of a reminder, accessed by index"""
        try:
            reminder = self.reminders[interaction.user.id][index - 1]
        except IndexError:
            raise IndexError("Couldn't find that reminder.")

        embed = (
            neo.Embed(description=reminder.content)
            .add_field(
                name="This reminder will be delivered at:",
                value=(f"<t:{int(reminder.end_time.timestamp())}>"),
            )
            .set_author(
                name="Viewing a reminder", icon_url=interaction.user.display_avatar
            )
        )
        await interaction.response.send_message(embed=embed)

    @remind_view.autocomplete("index")
    async def remind_view_autocomplete(self, interaction: discord.Interaction, current):
        if interaction.user.id not in self.bot.profiles:
            return []

        reminders = [rem.content for rem in self.reminders[interaction.user.id]]
        return generate_autocomplete_list(reminders, current)

    @app_commands.command(name="cancel")
    @app_commands.describe(index="A reminder index to remove")
    @is_registered_profile()
    async def remind_cancel(self, interaction: discord.Interaction, index: str):
        """Cancel a reminder by index"""
        if is_clear_all(index):
            reminders = self.reminders[interaction.user.id].copy()

        elif is_valid_index(index):
            try:
                reminders = [self.reminders[interaction.user.id].pop(int(index) - 1)]
            except IndexError:
                raise IndexError("One or more of the provided indices is invalid.")

        else:
            raise TypeError("Invalid input provided.")

        for reminder in reminders:
            await reminder.delete()
        await send_confirmation(interaction)

    @remind_cancel.autocomplete("index")
    async def remind_cancel_autocomplete(
        self, interaction: discord.Interaction, current
    ):
        if interaction.user.id not in self.bot.profiles:
            return []

        reminders = [rem.content for rem in self.reminders[interaction.user.id]]
        return generate_autocomplete_list(reminders, current, insert_wildcard=True)


async def setup(bot: neo.Neo):
    await bot.add_cog(Reminders(bot))

# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import discord
from discord import app_commands, utils

import neo
from neo.addons.auxiliary.reminders import ReminderEditModal, ReminderShowView
from neo.classes.app_commands import no_defer
from neo.classes.timer import periodic
from neo.modules import ButtonsMenu
from neo.tools import (
    generate_autocomplete_list,
    is_clear_all,
    is_valid_index,
    send_confirmation,
    shorten,
    try_or_none,
)
from neo.tools.checks import is_registered_profile_predicate
from neo.tools.time_parse import (
    TimedeltaWithYears,
    humanize_timedelta,
    parse_absolute,
    parse_relative,
)

# Maximum number of reminders per user
MAX_REMINDERS = 15
# Minimum number of total seconds in a repeating reminder
REPEATING_MINIMUM_SECONDS = 3600


class Reminder:
    # Max number of characters in a reminder's content
    MAX_LEN = 1000

    __slots__ = (
        "user_id",
        "reminder_id",
        "content",
        "epoch",
        "delta",
        "repeating",
        "bot",
        "_done",
    )

    def __init__(
        self,
        *,
        user_id: int,
        reminder_id: UUID,
        content: str,
        epoch: datetime,
        delta: timedelta,
        repeating: bool,
        bot: neo.Neo,
    ):
        self.user_id = user_id
        self.reminder_id = reminder_id
        self.content = content
        self.epoch = epoch
        self.delta = delta
        self.repeating = repeating

        self.bot = bot
        self._done = False

    @property
    def end_time(self):
        return self.epoch + self.delta

    async def poll(self, poll_time: datetime):
        if poll_time >= self.end_time:
            await self.update_repeating()
            await self.deliver()

    async def update_repeating(self) -> bool:
        """
        If this reminder is set to repeat, update the epoch and return True.

        Otherwise, return False.
        """
        if self.repeating is False:
            return False

        self.epoch += self.delta
        await self.bot.db.execute(
            """
            UPDATE
                reminders
            SET
                epoch=$1
            WHERE
                user_id=$2 AND
                reminder_id=$3
            """,
            self.epoch,
            self.user_id,
            self.reminder_id,
        )
        return True

    async def deliver(self):
        try:
            dest = self.bot.get_user(self.user_id, as_partial=True)

            embed = neo.Embed(
                title="Reminder Triggered", description=self.content
            )
            if self.repeating is True:
                embed.add_field(
                    name="Repeats at:",
                    value=f"<t:{self.end_time.timestamp():.0f}>",
                    inline=False,
                ).add_field(
                    name="Repeats every:",
                    value=f"`{humanize_timedelta(self.delta)}`",
                    inline=False,
                )

            await dest.send(
                content=self.content,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(
                    users=[discord.Object(self.user_id)]
                ),
            )
        except discord.HTTPException:
            # In the event of an HTTP exception, the reminder is deleted
            # regardless of its type
            await self.delete()

        finally:
            if self._done is False and self.repeating is False:
                # If the reminder is not a repeating reminder and it is not yet
                # marked as done, delete it
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
                reminder_id=$2
            """,
            self.user_id,
            self.reminder_id,
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
        delta: timedelta,
        repeating: bool,
        epoch: datetime,
    ):
        data = await self.bot.db.fetchrow(
            """
            INSERT INTO reminders (
                user_id,
                reminder_id,
                content,
                delta,
                repeating,
                epoch
            ) VALUES (
                $1, $2, $3, $4, $5, $6
            ) RETURNING *
            """,
            user_id,
            reminder_id,
            content,
            delta,
            repeating,
            epoch,
        )
        reminder = Reminder(bot=self.bot, **data)
        self.reminders[user_id].append(reminder)

    async def addon_interaction_check(
        self, interaction: discord.Interaction
    ) -> bool:
        return is_registered_profile_predicate(interaction)

    @app_commands.command(name="set")
    @app_commands.describe(
        when="When the reminder should be delivered. See this command's help entry for more info",
        content="The content to remind yourself about. Can be empty",
        repeat="Whether this reminder should repeat. See this command's help entry for more info",
    )
    async def reminder_set(
        self,
        interaction: discord.Interaction,
        when: str,
        content: app_commands.Range[str, 1, Reminder.MAX_LEN] = "…",
        repeat: bool = False,
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

        Providing a time within the current day will cause the reminder to[JOIN]
        be triggered the same day if the time has not passed yet, and will[JOIN]
        rollover to the next day if it has passed.

        Times can be expressed in either 24- or 12-hour time.

        **Note**
        If you have configured a timezone in your neo profile, it will be[JOIN]
        used to localize date/time. Otherwise, date/times will be in UTC.[JOIN]

        **__Relative__**
        Offsets have the following requirements:
        - Must be one of `years`, `weeks`, `days`, `hours`, `minutes`, and[JOIN]
        `seconds`
        - Not all time units have to be used
        - Time units have to be ordered by magnitude

        **Examples**
        /remind set `when: 5 years` `content: Hey, hello!`
        /remind set `when: 4h30m` `content: Check what time it is`
        /remind set `when: 3 weeks, 2 days` `content: Do something funny`

        **__Repeating Reminders__**
        Repeating reminders let you set a reminder to continuously be[JOIN]
        delivered with a set interval. Absolute and relative time formats[JOIN]
        are both supported in repeating reminders.

        **Repeating Absolute Reminders:**
        With repeating absolute reminders, you can select a time on the[JOIN]
        clock, and you will be reminded each day at this time. The[JOIN]
        interval can't be changed for absolute repeat reminders.

        **Repeating Relative Reminders:**
        With repeating relative reminders, you can set a custom interval[JOIN]
        for the reminder to repeat in. The `when` option will control how[JOIN]
        often the reminder repeats itself. Note that the interval must be[JOIN]
        at least 1 hour.
        """
        profile = self.bot.profiles[interaction.user.id]
        tz = profile.timezone or timezone.utc

        if len(self.reminders[interaction.user.id]) >= MAX_REMINDERS:
            raise ValueError("You've used up all of your reminder slots!")

        (time_data, _) = try_or_none(parse_relative, when) or parse_absolute(
            when, tz=tz
        )
        now = datetime.now(tz)

        message = "Your reminder will be delivered <t:{0}:R> [<t:{0}>]"
        match time_data:
            case TimedeltaWithYears():
                # Delta is provided, epoch time is now since it's the starting
                # point for the reminder
                delta = time_data
                epoch = now

                if repeat:
                    if delta.total_seconds() < REPEATING_MINIMUM_SECONDS:
                        raise ValueError("Interval must be at least 1 hour")
                    message = (
                        "Your reminder will be delivered every "
                        f"`{humanize_timedelta(delta)}`"
                    )

            case datetime():
                if repeat:
                    # Absolute repeats cycle every day
                    delta = timedelta(days=1)
                    # Subtracting the delta from the parsed datetime allows
                    # times from later in the current day to be triggered once
                    epoch = (time_data - delta).replace(second=1, microsecond=0)
                    message = (
                        "Your reminder will be delivered every day at "
                        f"<t:{epoch.timestamp():.0f}:t>"
                    )

                else:
                    delta = time_data - now
                    epoch = now

            case _:
                raise RuntimeError("Unknown error in time parsing")

        timestamp = int((now + delta).timestamp())
        await self.add_reminder(
            user_id=interaction.user.id,
            reminder_id=uuid4(),
            content=content,
            delta=delta,
            repeating=repeat,
            epoch=epoch,
        )
        await interaction.response.send_message(message.format(timestamp))

    @app_commands.command(name="list")
    async def remind_list(self, interaction: discord.Interaction):
        """Lists your active reminders"""
        reminders = self.reminders[interaction.user.id].copy()
        formatted_reminders: list[str] = []

        for index, reminder in enumerate(reminders, 1):
            formatted_reminders.append(
                "`{0} {1}` {2}\n➥ Triggers <t:{3}:R>".format(
                    index,
                    "\U0001F501"
                    if reminder.repeating
                    else "\u0031\uFE0F\u20E3",
                    utils.escape_markdown(shorten(reminder.content, 75)),
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
    @app_commands.rename(index="reminder")
    @app_commands.describe(index="A reminder index to view")
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
                inline=False,
            )
            .set_author(
                name="Viewing a reminder",
                icon_url=interaction.user.display_avatar,
            )
        )

        if reminder.repeating:
            embed.add_field(
                name="This reminder will repeat every:",
                value=f"`{humanize_timedelta(reminder.delta)}`",
            )

        view = ReminderShowView(self.bot.db, reminder=reminder)

        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="edit")
    @app_commands.rename(index="reminder")
    @app_commands.describe(index="A reminder index to edit")
    @no_defer
    async def remind_edit(self, interaction: discord.Interaction, index: int):
        """Edit the content of a reminder, accessed by index"""
        try:
            reminder = self.reminders[interaction.user.id][index - 1]
        except IndexError:
            raise IndexError("Couldn't find that reminder.")

        modal = ReminderEditModal(self.bot.db, reminder=reminder)
        await interaction.response.send_modal(modal)

    @remind_view.autocomplete("index")
    @remind_edit.autocomplete("index")
    async def remind_view_edit_autocomplete(
        self, interaction: discord.Interaction, current
    ):
        if interaction.user.id not in self.bot.profiles:
            return []

        reminders = [rem.content for rem in self.reminders[interaction.user.id]]
        return generate_autocomplete_list(reminders, current)

    @app_commands.command(name="cancel")
    @app_commands.rename(index="reminder")
    @app_commands.describe(index="A reminder index to remove")
    async def remind_cancel(self, interaction: discord.Interaction, index: str):
        """Cancel a reminder by index"""
        if is_clear_all(index):
            reminders = self.reminders[interaction.user.id].copy()

        elif is_valid_index(index):
            try:
                reminders = [
                    self.reminders[interaction.user.id].pop(int(index) - 1)
                ]
            except IndexError:
                raise IndexError(
                    "One or more of the provided indices is invalid."
                )

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
        return generate_autocomplete_list(
            reminders, current, insert_wildcard=True
        )


async def setup(bot: neo.Neo):
    await bot.add_cog(Reminders(bot))

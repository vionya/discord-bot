# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
from __future__ import annotations

import asyncio
from bisect import insort
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import discord
from discord import app_commands, utils

import fuchsia
from fuchsia.classes.app_commands import no_defer
from fuchsia.classes.timer import periodic
from fuchsia.modules import ButtonsMenu
from fuchsia.tools import (
    generate_autocomplete_list,
    is_clear_all,
    is_valid_index,
    iter_autocomplete,
    send_confirmation,
    shorten,
    try_or_none,
)
from fuchsia.tools.checks import is_registered_profile_predicate
from fuchsia.tools.time_parse import (
    TimedeltaWithYears,
    humanize_timedelta,
    parse_absolute,
    parse_relative,
)

from .auxiliary.reminders import (
    ReminderDeliveryView,
    ReminderEditModal,
    ReminderShowView,
)

# Maximum number of reminders per user
MAX_REMINDERS = 100
# Minimum number of total seconds in a repeating reminder
REPEATING_MINIMUM_SECONDS = 60


class Reminder:
    # Max number of characters in a reminder's content
    MAX_LEN = 1000

    # Number of seconds to keep a reminder alive after it's delivered
    KEEPALIVE_TIME = 300

    # Delta for KEEPALIVE_TIME seconds
    KEEPALIVE_DELTA = timedelta(seconds=KEEPALIVE_TIME)

    user_id: int
    reminder_id: UUID
    content: str
    epoch: datetime
    delta: timedelta
    repeating: bool
    deliver_in: int | None
    bot: fuchsia.Fuchsia

    _done: bool
    _kill_at: datetime

    __slots__ = (
        "user_id",
        "reminder_id",
        "content",
        "epoch",
        "delta",
        "repeating",
        "deliver_in",
        "bot",
        "_done",
        "_kill_at",
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
        deliver_in: int | None,
        bot: fuchsia.Fuchsia,
    ):
        self.user_id = user_id
        self.reminder_id = reminder_id
        self.content = content
        self.epoch = epoch
        self.delta = delta
        self.repeating = repeating
        self.deliver_in = deliver_in

        self.bot = bot
        self._done = False
        self._kill_at = self.end_time + Reminder.KEEPALIVE_DELTA

    @property
    def end_time(self):
        return self.epoch + self.delta

    @property
    def alive(self):
        return not self._done

    async def poll(self, poll_time: datetime):
        # the reminder will be kept alive for KEEPALIVE_TIME seconds after it
        # has reached its epoch
        if poll_time >= self._kill_at:
            await self.delete()

        elif poll_time >= self.end_time and not self._done:
            if self.repeating:
                await self.reschedule()
            await self.deliver()

    async def reschedule(self):
        """
        Update the epoch of this reminder

        Also updates the kill time and done marker accordingly
        """
        self.epoch += self.delta
        self._kill_at = self.end_time + Reminder.KEEPALIVE_DELTA
        self._done = False
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

    async def deliver(self):
        try:
            dest = self.bot.get_user(self.user_id, as_partial=True)
            if self.deliver_in is not None:
                dest = self.bot.get_channel(self.deliver_in) or dest

            # self.deliver_in can only be set from a Messageable, so this should
            # never fail and if it does I will cry
            assert isinstance(dest, discord.abc.Messageable)

            embed = fuchsia.Embed(
                title="Reminder Triggered", description=self.content
            )
            if self.repeating is True:
                embed.add_field(
                    name="Repeats at:",
                    value=f"<t:{self.end_time.timestamp():.0f}>",
                    inline=True,
                ).add_field(
                    name="Repeats every:",
                    value=f"`{humanize_timedelta(self.delta)}`",
                    inline=True,
                )

            content = shorten(self.content, 75)
            # mention the user if there is an existing channel we want to send in
            if isinstance(
                dest,
                discord.abc.GuildChannel
                | discord.Thread
                | discord.abc.PrivateChannel,
            ):
                content = f"<@{self.user_id}> {content}"

            kwargs = {
                "content": content,
                "embed": embed,
                "allowed_mentions": discord.AllowedMentions(
                    users=[discord.Object(self.user_id)]
                ),
            }

            if not self.repeating:
                view = ReminderDeliveryView(reminder=self)
                kwargs["view"] = view

            msg = await dest.send(**kwargs)
            if not self.repeating:
                # backpatch the message object for edit on timeout
                view.message = msg
        except discord.HTTPException:
            # In the event of an HTTP exception, the reminder is deleted
            # regardless of its type
            await self.delete()

        finally:
            if self._done is False and self.repeating is False:
                # If the reminder is not a repeating reminder and it is not yet
                # marked as done, mark it as done
                self._done = True

    async def delete(self):
        """Remove this reminder from the database"""
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


class Reminders(fuchsia.Addon, app_group=True, group_name="remind"):
    """Commands for managing reminders"""

    def __init__(self, bot: fuchsia.Fuchsia):
        self.bot = bot
        self.reminders: dict[int, list[Reminder]] = defaultdict(list)
        asyncio.create_task(self.__ainit__())

    async def __ainit__(self):
        await self.bot.wait_until_ready()

        # initially fetch reminders sorted by end time
        for record in await self.bot.db.fetch(
            "SELECT * FROM reminders ORDER BY epoch + delta ASC"
        ):
            reminder = Reminder(bot=self.bot, **record)
            self.reminders[record["user_id"]].append(reminder)

        self.poll_reminders.start()

    @fuchsia.Addon.recv("profile_delete")
    async def handle_deleted_profile(self, user_id: int):
        for reminder in self.reminders.pop(user_id, []):
            await reminder.delete()

    @fuchsia.Addon.recv("reminder_removed")
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
        deliver_in: int | None,
    ):
        data = await self.bot.db.fetchrow(
            """
            INSERT INTO reminders (
                user_id,
                reminder_id,
                content,
                delta,
                repeating,
                epoch,
                deliver_in
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7
            ) RETURNING *
            """,
            user_id,
            reminder_id,
            content,
            delta,
            repeating,
            epoch,
            deliver_in,
        )
        reminder = Reminder(bot=self.bot, **data)
        insort(self.reminders[user_id], reminder, key=lambda r: r.end_time)

    async def addon_interaction_check(
        self, interaction: discord.Interaction
    ) -> bool:
        return is_registered_profile_predicate(interaction)

    @iter_autocomplete(("1d", "1w", "1mo", "1y"), param="repeat")
    @app_commands.command(name="set")
    @app_commands.describe(
        when="When the reminder should be delivered. See this command's help entry for more info",
        content="The content to remind yourself about. Can be empty",
        repeat="When this reminder should repeat. Provided options are suggestions",
        send_here="Whether this reminder should be sent to you in this channel",
    )
    @app_commands.rename(repeat="repeat-every", send_here="send-here")
    async def reminder_set(
        self,
        interaction: discord.Interaction,
        when: str,
        content: app_commands.Range[str, 1, Reminder.MAX_LEN] = "…",
        repeat: str | None = None,
        send_here: bool | None = None,
    ):
        """
        Schedule a reminder

        `when` may be either absolute or relative.

        ## Absolute
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

        ### Note
        If you have configured a timezone in your fuchsia profile, it will be[JOIN]
        used to localize date/time. Otherwise, date/times will be in UTC.[JOIN]

        ## Relative
        Offsets have the following requirements:
        - Must be in terms of `years`, `months`, `weeks`, `days`, `hours`,[JOIN]
        `minutes`, and `seconds`
        - Not all time units have to be used
        - Time units have to be ordered by magnitude

        ### Examples
        /remind set `when: 5 years` `content: Hey, hello!`
        /remind set `when: 4h30m` `content: Check what time it is`
        /remind set `when: 3 weeks, 2 days` `content: Do something funny`

        ## Repeating Reminders
        Repeating reminders let you set a reminder to continuously be[JOIN]
        delivered with a set interval. **Only absolute reminders are[JOIN]
        allowed to be repeating reminders.**

        To create a repeating reminder, you can set `when` to any given[JOIN]
        as normal, and provide a relative offset to `repeat-every`.

        The `repeat-every` offset looks like a relative reminder format[JOIN]
        which is described above.
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
                if repeat:
                    raise ValueError("Relative reminders cannot repeat")

                # Delta is provided, epoch time is now since it's the starting
                # point for the reminder
                delta = time_data
                epoch = now

            case datetime():
                if repeat:
                    # Parse the repetition frequency
                    delta = parse_relative(repeat)[0]
                    if delta.total_seconds() < REPEATING_MINIMUM_SECONDS:
                        raise ValueError(
                            "Reminders may repeat no more than once an minute"
                        )

                    # Subtracting the delta from the parsed datetime allows
                    # times from later in the current day to be triggered once
                    epoch = (time_data - delta).replace(second=1, microsecond=0)
                    message = (
                        "Your reminder will be delivered every {0}, starting"
                        " <t:{1:.0f}>"
                    ).format(
                        humanize_timedelta(delta), (epoch + delta).timestamp()
                    )

                else:
                    delta = time_data - now
                    epoch = now

            case _:
                raise RuntimeError("Unknown error in time parsing")

        timestamp = int((now + delta).timestamp())
        in_channel = (
            send_here if send_here is not None else profile.reminders_in_channel
        )

        await self.add_reminder(
            user_id=interaction.user.id,
            reminder_id=uuid4(),
            content=content,
            delta=delta,
            repeating=bool(repeat),
            epoch=epoch,
            deliver_in=interaction.channel_id if in_channel is True else None,
        )
        await interaction.response.send_message(message.format(timestamp))

    @app_commands.command(name="list")
    async def remind_list(self, interaction: discord.Interaction):
        """Lists your active reminders"""
        reminders = self.reminders[interaction.user.id].copy()
        formatted_reminders: list[str] = []

        # sort by next to trigger, ascending
        for reminder in sorted(reminders, key=lambda r: r.end_time):
            # don't display dying reminders
            if not reminder.alive:
                continue
            content = utils.escape_markdown(
                shorten("".join(reminder.content.splitlines()), 75)
            )
            formatted_reminders.append(
                "- {0} (<t:{1}:R>) {2}".format(
                    (
                        "\U0001F501"
                        if reminder.repeating
                        else "\u0031\uFE0F\u20E3"
                    ),
                    int(reminder.end_time.timestamp()),
                    content,
                )
            )

        menu = ButtonsMenu.from_iterable(
            formatted_reminders or ["No reminders"],
            per_page=10,
            use_embed=True,
            template_embed=fuchsia.Embed()
            .set_author(
                name=f"{interaction.user}'s reminders",
                icon_url=interaction.user.display_avatar,
            )
            .set_footer(text=f"{len(reminders)}/{MAX_REMINDERS} slots used"),
        )
        await menu.start(interaction)

    @app_commands.command(name="view")
    @app_commands.rename(index="reminder")
    @app_commands.describe(index="A reminder to view")
    async def remind_view(self, interaction: discord.Interaction, index: int):
        """View the full content of a reminder"""
        try:
            reminder = self.reminders[interaction.user.id][index - 1]
        except IndexError:
            raise IndexError("Couldn't find that reminder.")

        embed = (
            fuchsia.Embed(description=reminder.content)
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
                inline=False,
            )

        embed.add_field(
            name="Reminder ID", value=f"`{reminder.reminder_id}`", inline=False
        )

        view = ReminderShowView(self.bot.db, reminder=reminder)

        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="edit")
    @app_commands.rename(index="reminder")
    @app_commands.describe(index="A reminder to edit")
    @no_defer
    async def remind_edit(self, interaction: discord.Interaction, index: int):
        """Edit the content of a reminder"""
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
        return generate_autocomplete_list(reminders, current, show_numbers=True)

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
        await send_confirmation(interaction, predicate="cancelled reminder")

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


async def setup(bot: fuchsia.Fuchsia):
    await bot.add_cog(Reminders(bot))

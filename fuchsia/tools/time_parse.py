# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 vionya
"""
Implements an extremely simple mechanism for parsing a datetime object out of
a string of text.
"""
import re
from datetime import datetime, timedelta, tzinfo
from typing import NoReturn

from dateutil.parser import ParserError, parse

RELATIVE_FORMATS = re.compile(
    r"""
    ((?P<years>[0-9]{1,2})\s?(?:y(ears?)?,?))?         # Parse years, allow 1-2 digits
    \s?((?P<months>[0-9]{1,2})\s?(?:mo(nths?)?))?      # Parse months, allow 1-2 digits
    \s?((?P<weeks>[0-9]{1,2})\s?(?:w(eeks?)?,?))?      # Parse weeks, allow 1-2 digits
    \s?((?P<days>[0-9]{1,4})\s?(?:d(ays?)?,?))?        # Parse days, allow 1-4 digits
    \s?((?P<hours>[0-9]{1,4})\s?(?:h(ours?)?,?))?      # Parse hours, allow 1-4 digits
    \s?((?P<minutes>[0-9]{1,4})\s?(?:m(inutes?)?,?))?  # Parse minutes, allow 1-4 digits
    \s?((?P<seconds>[0-9]{1,4})\s?(?:s(econds?)?))?    # Parse seconds, allow 1-4 digits
    """,
    re.X | re.I,
)


def humanize_timedelta(delta: timedelta) -> str:
    """
    Humanizes the components of a timedelta.

    Given a timedelta `delta`, this function returns a textual expansion of the
    time delta in human-readable form.

    Example:
    ```py
    >>> delta = timedelta(days=367, minutes=65, seconds=2)
    >>> humanize_timedelta(delta)
    "1 years, 2 days, 1 hours, 5 minutes, 2 seconds"
    ```

    :param delta: The timedelta to humanize
    :type delta: ``timedelta``

    :return: A human-readable representation of the provided delta
    :rtype: ``str``
    """
    fmt_pairs = (
        (delta.days // 365, "years"),
        (delta.days % 365, "days"),
        (delta.seconds // 3600, "hours"),
        (delta.seconds % 3600 // 60, "minutes"),
        (delta.seconds % 3600 % 60, "seconds"),
    )
    return ", ".join(f"{p[0]} {p[1]}" for p in fmt_pairs if p[0] != 0)


class TimedeltaWithYears(timedelta):
    def __new__(
        cls,
        *,
        years: float = 0,
        months: float = 0,
        weeks: float = 0,
        days: float = 0,
        hours: float = 0,
        minutes: float = 0,
        seconds: float = 0,
    ):
        # `months` is unfortunately just a rough estimate, might revisit later
        days = days + (years * 365) + (months * 31)
        return super().__new__(
            cls,
            weeks=weeks,
            days=days,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
        )


def parse_absolute(string: str, *, tz: tzinfo) -> tuple[datetime, str]:
    """
    Attempts to parse a datetime from a string of text.

    This function leverages `dateutil.parser.parse` to parse datetimes from
    its input.

    :param string: The string to attempt to parse a datetime from
    :type string: ``str``

    :param tz: The timezone to set the returnd datetime to
    :type tz: ``datetime.tzinfo``

    :return: A tuple with the parsed datetime and the unparsed string content
    :rtype: ``tuple[datetime.datetime, str]``

    :raises ValueError: If no valid datetime could be parsed

    :raises RuntimeError: If there was an unknown underlying exception
    """
    try:
        dt = parse(string, default=datetime.now(tz))
        return (dt, string)
    except ParserError:
        raise ValueError("An invalid date format was provided.")
    except Exception:
        raise RuntimeError("There was an unknown error :(")


def parse_relative(
    string: str,
) -> tuple[TimedeltaWithYears, str] | NoReturn:
    """
    Attempts to parse a relative time offset from a string of text.

    The `string` argument is matched against the `RELATIVE_FORMATS` regex, which
    attempts to group all time denominations. If successful, a timedelta is
    returned

    :param string: The string to attempt to parse
    :type string: ``str``

    :return: A tuple with the parsed timedelta and the unparsed string content
    :rtype: ``tuple[TimedeltaWithYears, Str]``

    :raises ValueError: If no valid delta could be parsed
    """
    parsed = RELATIVE_FORMATS.match(string)

    if parsed and any(parsed.groups()):
        data = {k: float(v) for k, v in parsed.groupdict().items() if v}
        return (
            TimedeltaWithYears(**data),
            string.removeprefix(parsed[0]).strip(),
        )

    else:  # Nothing matched
        raise ValueError("Failed to find a valid offset.")

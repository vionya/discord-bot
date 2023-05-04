# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
import traceback
from enum import Enum
from logging import Formatter, LogRecord
from types import TracebackType

# Taken from typeshed
ExcInfo = tuple[type[BaseException], BaseException, TracebackType]
OptExcInfo = ExcInfo | tuple[None, None, None]


def format_exception(exc: BaseException | OptExcInfo) -> str:
    if isinstance(exc, tuple) and all(exc):
        exc_info = exc
    elif isinstance(exc, BaseException):
        exc_info = (type(exc), exc, exc.__traceback__)
    else:
        return ""

    return "".join(traceback.format_exception(*exc_info)).rstrip()


def shorten(text: str, width: int) -> str:
    """
    Shorten a string `text` to length `width`

    If a string's length is <= `width`, it is returned as-is. Otherwise, the
    string is shortened to length `width - 1` and an ellipsis ("…") is appended.

    :param text: The text content to shorten
    :type text: ``str``

    :param width: The maximum length of the shortened text
    :type width: ``int``

    :rtype: ``str``
    """
    if len(text) > width:
        text = text[: width - 1] + "…"
    return text


def humanize_snake_case(text: str) -> str:
    """
    Transform a snake_case variable name to a human-friendly representation

    Example: given "snake_case", this function returns "Snake Case".

    :param text: The snake-cased text to convert
    :type text: ``str``

    :rtype: ``str``
    """
    return text.replace("_", " ").title()


class Table:
    built_columns: str
    built_rows: str

    __slots__ = (
        "columns",
        "rows",
        "widths",
        "border",
        "built_columns",
        "built_rows",
    )

    def __init__(self):
        self.columns: list[str] = []
        self.rows: list[list[str]] = []
        self.widths: list[int] = []

    def init_columns(self, *columns: str):
        self.columns = [*columns]
        # 4 spaces of padding around each column
        self.widths = [len(col) + 4 for col in columns]

    def add_row(self, *row: str):
        if len(row) > len(self.columns):
            raise ValueError("Row has too many columns")

        self.rows.append([*row])
        for index, item in enumerate(row):
            if (len(item) + 4) > self.widths[index]:
                # If the length of the value exceeds the initial column width,
                # it's re-calculated to meet the maximum width in the data
                self.widths[index] = len(item) + 4

    def build(self):
        cols: list[str] = []
        for index, col in enumerate(self.columns):
            # Center the column header within the padding determined by
            # the added rows
            cols.append(col.center(self.widths[index]))
        self.built_columns = "|" + "|".join(cols) + "|"

        # Put a "+" at each column separator, in between "-"s
        separator = "+".join("-" * w for w in self.widths)
        self.border = "+" + separator + "+"

        rows: list[str] = []
        for row in self.rows:
            final_row: list[str] = []
            for index, item in enumerate(row):
                # For each row, repeat the same process as done for the
                # column headers, centering based on calculated width
                final_row.append(item.center(self.widths[index]))
            rows.append("|" + "|".join(final_row) + "|")
        self.built_rows = "\n".join(rows)

    def display(self):
        self.build()
        return (
            f"{self.border}\n"
            f"{self.built_columns}\n"
            f"{self.border}\n"
            f"{self.built_rows}\n"
            f"{self.border}"
        )


class Color(Enum):
    Reset = "0"
    Purple = "38;2;162;155;254"
    Green = "38;2;186;230;126"
    Cyan = "38;2;92;207;230"
    Grey = "38;2;112;122;140"
    Silver = "38;2;92;103;115"
    Tan = "38;2;255;230;179"
    Orange = "38;2;255;167;89"
    Red = "38;2;255;51;51"

    def __new__(cls, value):
        obj = object.__new__(cls)
        obj._value_ = f"\033[{value}m"
        return obj

    def __call__(self, string: str):  # Is this considered a crime?
        """
        Apply the ANSI color to the provided string

        Trailing resets are provided as well

        ```py
        >>> Color.PURPLE("foo")
        "\\033[38;2;162;155;254mfoo\\033[0m"
        ```
        """
        return f"{self.value}{string}{Color.Reset.value}"


class NeoLoggingFormatter(Formatter):
    COLORS = {
        "DEBUG": Color.Silver,
        "INFO": Color.Green,
        "WARNING": Color.Tan,
        "ERROR": Color.Orange,
        "CRITICAL": Color.Red,
    }

    def __init__(self, **kwargs):
        kwargs["style"] = "{"
        kwargs["datefmt"] = Color.Cyan("%d-%m-%Y %H:%M:%S")
        super().__init__(**kwargs)

    def format(self, record: LogRecord):
        record.asctime = Color.Cyan(self.formatTime(record, self.datefmt))
        record.msg = Color.Grey(record.msg)
        record.name = Color.Purple(record.name)
        record.levelname = self.COLORS[record.levelname](record.levelname)
        return super().format(record)


def full_timestamp(timestamp: float) -> str:
    """
    Returns a detailed Discord timestamp string
    Timestamps are in the form "<t:xxx:d> <t:xxx:T>"
    :param timestamp: The timestamp to convert to string
    :type timestamp: ``float``
    :return: The Discord-formatted timestamp string
    :rtype: ``str``
    """
    date = f"<t:{timestamp:.0f}:d>"
    time = f"<t:{timestamp:.0f}:T>"
    return date + " " + time

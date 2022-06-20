# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
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


class Table:
    built_columns: str
    built_rows: str

    __slots__ = ("columns", "rows", "widths", "border", "built_columns", "built_rows")

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
    RESET = "0"
    PURPLE = "38;2;162;155;254"
    GREEN = "38;2;186;230;126"
    CYAN = "38;2;92;207;230"
    GREY = "38;2;112;122;140"
    SILVER = "38;2;92;103;115"
    TAN = "38;2;255;230;179"
    ORANGE = "38;2;255;167;89"
    RED = "38;2;255;51;51"

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
        return f"{self.value}{string}{Color.RESET.value}"


class NeoLoggingFormatter(Formatter):
    COLORS = {
        "DEBUG": Color.SILVER,
        "INFO": Color.GREEN,
        "WARNING": Color.TAN,
        "ERROR": Color.ORANGE,
        "CRITICAL": Color.RED,
    }

    def __init__(self, **kwargs):
        kwargs["style"] = "{"
        kwargs["datefmt"] = Color.CYAN("%d-%m-%Y %H:%M:%S")
        super().__init__(**kwargs)

    def format(self, record: LogRecord):
        record.asctime = Color.CYAN(self.formatTime(record, self.datefmt))
        record.msg = Color.GREY(record.msg)
        record.name = Color.PURPLE(record.name)
        record.levelname = self.COLORS[record.levelname](record.levelname)
        return super().format(record)

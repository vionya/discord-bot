# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
import asyncio
import logging
import os
import signal

import toml

try:
    import uvloop  # type: ignore
    uvloop.install()
except ImportError:
    pass

from neo import Neo
from neo.classes.formatters import NeoLoggingFormatter

from . import runtime

# Sect: Logging
if os.name == "nt":
    os.system("color")  # Enable ANSI escapes on win32

loggers = [logging.getLogger("discord"),
           logging.getLogger("neo")]

formatter = NeoLoggingFormatter(
    fmt="[{asctime}] [{levelname} {name} {funcName}] {message}")
handler = logging.StreamHandler()
handler.setFormatter(formatter)

[(logger.setLevel(logging.INFO),
  logger.addHandler(handler)) for logger in loggers]

# /Sect: Logging

# Execute all patches defined in runtime.py
runtime.patch_all()

# Sect: Running bot


async def main():
    with open("config.toml", "r") as file:
        config = toml.load(file)

    neo = Neo(config)

    await neo.start()

if __name__ == "__main__":
    asyncio.run(main())

# /Sect: Running bot

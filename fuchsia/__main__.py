# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 sardonicism-04
import asyncio
import logging
import os
from typing import cast

import toml

from fuchsia.types.config import FuchsiaConfig

try:
    import uvloop  # type: ignore

    uvloop.install()
except ImportError:
    pass

from fuchsia import Fuchsia
from fuchsia.tools.formatters import FuchsiaLoggingFormatter

from . import runtime

# Sect: Logging
if os.name == "nt":
    os.system("color")  # Enable ANSI escapes on win32

loggers = [logging.getLogger("discord"), logging.getLogger("fuchsia")]

formatter = FuchsiaLoggingFormatter(
    fmt="[{asctime}] [{levelname} {name} {funcName}] {message}"
)
handler = logging.StreamHandler()
handler.setFormatter(formatter)

for logger in loggers:
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

# /Sect: Logging

# Execute all patches defined in runtime.py
runtime.patch_all()

# Sect: Running bot


async def main():
    with open("config.toml", "r") as file:
        config: FuchsiaConfig = cast(FuchsiaConfig, toml.load(file))

    fuchsia = Fuchsia(config)

    await fuchsia.start()


if __name__ == "__main__":
    asyncio.run(main())

# /Sect: Running bot

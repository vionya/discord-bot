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
from neo.types.formatters import NeoLoggingFormatter

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

# Large amount of the code for loop control based on discord.Client.run


def cleanup_loop(loop: asyncio.AbstractEventLoop):
    tasks = [*filter(lambda t: not t.cancelled(), asyncio.all_tasks(loop))]

    for task in tasks:
        task.cancel()

    loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))

    for task in filter(lambda t: not t.cancelled(), tasks):
        if task.exception():
            loop.call_exception_handler({
                "message": "Unhandled exception during shutdown",
                "exception": task.exception(),
                "task": task
            })
    loggers[1].info(f"Cancelled {len(tasks)} tasks")

    loop.run_until_complete(loop.shutdown_asyncgens())
    loggers[1].info("Shutdown all async generators")


def main():
    with open("config.toml", "r") as file:
        config = toml.load(file)

    loop = asyncio.new_event_loop()
    bot = Neo(config, loop=loop)

    try:
        loop.add_signal_handler(signal.SIGINT, lambda: loop.stop())
        loop.add_signal_handler(signal.SIGTERM, lambda: loop.stop())
    except NotImplementedError:
        pass

    done_callback = lambda _: loop.stop()  # fmt: off

    async def runner():
        try:
            await bot.start()
        finally:
            if not bot.is_closed():
                await bot.close()

    task = loop.create_task(runner())
    task.add_done_callback(done_callback)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        loggers[1].info("Terminating loop by keyboard interrupt")
    finally:
        task.remove_done_callback(done_callback)
        cleanup_loop(loop)
        loggers[1].info("Closing the event loop")
        loop.close()

    if not task.cancelled():
        try:
            return task.result()
        except KeyboardInterrupt:
            return None

if __name__ == "__main__":
    main()

# /Sect: Running bot

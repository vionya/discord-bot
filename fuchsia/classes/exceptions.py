# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
class FuchsiaException(Exception):
    """The base class that all fuchsia-related exceptions derive from"""


class DisabledCommand(FuchsiaException):
    """Raised when a command is disabled in the current context"""

    def __init__(self, command: str):
        self.command = command

    def __str__(self):
        return f"Command `{self.command}` is disabled in this context."


class DisabledChannel(FuchsiaException):
    """Raised when commands are disabled in the current channel"""

    def __str__(self):
        return "Commands are disabled in this channel."

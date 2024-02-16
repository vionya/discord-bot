from typing import Any

from discord import app_commands
from discord.ext import commands

AnyCommand = (
    commands.Command[Any, ..., Any]
    | app_commands.Command[Any, ..., Any]
    | app_commands.Group
    | app_commands.ContextMenu
)

# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
import argparse
import logging

import discord
from discord.ext import commands

from neo.classes.formatters import format_exception
from neo.classes.hybrid_command import AutoEphemeralHybridCommand
from neo.modules.args.commands import ArgCommand, ArgGroup
from neo.tools import Patcher

logger = logging.getLogger("neo")

guild = Patcher(discord.Guild)
group = Patcher(commands.Group)
message = Patcher(discord.Message)
missing_required = Patcher(commands.MissingRequiredArgument)
argument_error = Patcher(argparse.ArgumentError)
view = Patcher(discord.ui.View)
hybrid_command = Patcher(commands.hybrid)


@guild.attribute()
async def fetch_member(self: discord.Guild, member_id, *, cache=False):
    data = await self._state.http.get_member(self.id, member_id)
    mem = discord.Member(data=data, state=self._state, guild=self)
    if cache:
        self._members[mem.id] = mem
    return mem


@group.attribute()
def arg_command(self, **kwargs):
    def inner(func):
        cls = kwargs.get("cls", ArgCommand)
        kwargs["parent"] = self
        result = cls(func, **kwargs)
        self.add_command(result)
        return result

    return inner


@group.attribute()
def arg_group(self, **kwargs):
    def inner(func):
        cls = kwargs.get("cls", ArgGroup)
        kwargs["parent"] = self
        result = cls(func, **kwargs)
        self.add_command(result)
        return result

    return inner


@group.attribute(name="__init__")
def group_init(self, *args, **attrs) -> None:
    attrs.setdefault("case_insensitive", True)
    self.invoke_without_command = attrs.pop("invoke_without_command", False)
    super(commands.Group, self).__init__(*args, **attrs)


@message.attribute()
async def add_reaction(self, emoji):
    emoji = discord.message.convert_emoji_reaction(emoji)
    try:
        await self._state.http.add_reaction(self.channel.id, self.id, emoji)
    except discord.HTTPException as e:
        if e.code == 90001:
            return  # Ignore errors from trying to react to blocked users
        raise e  # If not 90001, re-raise


@missing_required.attribute(name="__init__")
def missing_required_init(self, param):
    self.param = param
    super(commands.MissingRequiredArgument, self).__init__(
        f"Missing required argument(s): `{param.name}`"
    )


@argument_error.attribute()
def __str__(self):
    if self.argument_name is None:
        format = "{.message}"
    else:
        format = "Argument `{0.argument_name}`: {0.message}"
    return format.format(self)


@view.attribute()
async def on_error(self, interaction, error, item):
    if isinstance(error, discord.Forbidden):
        if error.code == 50083:  # Tried to perform action in archived thread
            return
    logger.error(format_exception(error))


hybrid_command.attribute(name="HybridCommand", value=AutoEphemeralHybridCommand)


def patch_all() -> None:
    guild.patch()
    group.patch()
    message.patch()
    missing_required.patch()
    argument_error.patch()
    view.patch()
    hybrid_command.patch()

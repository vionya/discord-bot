# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, ParamSpec, TypeVar, cast

from discord import AppCommandOptionType, Interaction, app_commands
from discord.ext.commands import Cog

if TYPE_CHECKING:
    from discord.app_commands.commands import CommandCallback
    from neo import Neo

T = TypeVar("T")
P = ParamSpec("P")

GroupT = TypeVar("GroupT", bound=app_commands.Group | Cog)


def get_ephemeral(
    interaction: Interaction,
    namespace: Optional[app_commands.Namespace | dict[str, Any]] = None,
) -> bool:
    """Given an Interaction and a namespace, determines whether or not the output should be ephemeral"""
    if TYPE_CHECKING:
        bot = cast(Neo, interaction.client)
    else:
        bot = interaction.client

    user = interaction.user

    default = True
    if user.id in bot.profiles:
        default = bot.profiles[user.id].default_ephemeral

    passed_option = getattr(namespace, "private", None)
    if isinstance(namespace, dict):
        passed_option = namespace.pop("private", None)
    ephemeral = default if passed_option is None else passed_option
    return ephemeral


class AutoEphemeralAppCommand(app_commands.Command[GroupT, P, T]):
    def __init__(
        self,
        *,
        name: str,
        description: str,
        callback: CommandCallback[GroupT, P, T],
        parent: Optional[app_commands.Group] = None,
        guild_ids: Optional[list[int]] = None,
        nsfw: bool = False,
        extras: dict[Any, Any] = {},
    ):
        super().__init__(
            name=name,
            description=description,
            callback=callback,
            parent=parent,
            guild_ids=guild_ids,
            nsfw=nsfw,
            extras=extras,
        )

        # Inject a `private` parameter to every app commmand
        self._params["private"] = app_commands.transformers.CommandParameter(
            name="private",
            description="Whether or not to send the command result privately",
            required=False,
            default=None,
            type=AppCommandOptionType.boolean,
        )

    async def _invoke_with_namespace(
        self,
        interaction: Interaction,
        namespace: app_commands.Namespace,
    ) -> T:
        if not getattr(self.callback, "no_defer", False):
            await interaction.response.defer()

        if not await self._check_can_run(interaction):
            raise app_commands.CheckFailure(
                f"The check functions for command {self.name!r} failed."
            )

        transformed_values = await self._transform_arguments(interaction, namespace)
        interaction.namespace.ephemeral = get_ephemeral(interaction, namespace)  # type: ignore

        transformed_values.pop("private", None)
        return await self._do_call(interaction, transformed_values)

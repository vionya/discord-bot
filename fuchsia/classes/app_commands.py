# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 vionya
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional, ParamSpec, TypeVar, cast

from discord import AppCommandOptionType, Interaction, app_commands
from discord.ext.commands import Cog

if TYPE_CHECKING:
    from collections.abc import Callable

    from discord.app_commands.commands import CommandCallback

    from fuchsia import Addon, Fuchsia

T = TypeVar("T")
P = ParamSpec("P")

GroupT = TypeVar("GroupT", bound=app_commands.Group | Cog)


def get_ephemeral(
    interaction: Interaction,
    namespace: Optional[app_commands.Namespace | dict[str, Any]] = None,
) -> bool:
    """Given an Interaction and a namespace, determines whether or not the output should be ephemeral"""
    if TYPE_CHECKING:
        bot = cast(Fuchsia, interaction.client)
    else:
        bot = interaction.client

    user = interaction.user

    # whether users who have no profile should get ephemeral responses by default
    default = False
    if user.id in bot.profiles:
        default = bot.profiles[user.id].default_ephemeral

    passed_option = getattr(namespace, "private", None)
    if isinstance(namespace, dict):
        passed_option = namespace.pop("private", None)
    ephemeral = default if passed_option is None else passed_option
    return ephemeral


# This functionality could just be patched into app commands as a parameter, but
# doing it this way stops the type checker from being angry about it
def no_defer(callback: Callable[..., Any]) -> Callable[..., Any]:
    """Decorates a callback, preventing the app command from being automatically deferred"""
    setattr(callback, "no_defer", True)
    return callback


class AutoEphemeralAppCommand(app_commands.Command[GroupT, P, T]):
    addon: Optional[Addon]

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
        **rest,  # handle any new arguments that may be implemented upstream
    ):
        super().__init__(
            name=name,
            description=description,
            callback=callback,
            parent=parent,
            guild_ids=guild_ids,
            nsfw=nsfw,
            extras=extras,
            **rest,
        )
        self.addon = None

        # Inject a `private` parameter to every app commmand
        self._params["private"] = app_commands.transformers.CommandParameter(
            name="private",
            description="Whether or not to send the command result privately",
            required=False,
            default=None,
            type=AppCommandOptionType.boolean,
        )

    async def _check_can_run(self, interaction: Interaction) -> bool:
        # This could be ignored and just rely on an `interaction_check`
        # method in `self.binding`, but I'm not sure if the modifications
        # I've done would mess with it so I'm just not touching it
        if hasattr(self, "addon") and self.addon is not None:
            # If the addon interaction check fails, the error is
            # propogated up to the tree error handler
            ret = await self.addon.addon_interaction_check(interaction)
            if ret is False:
                return False

        return await super()._check_can_run(interaction)

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

        transformed_values = await self._transform_arguments(
            interaction, namespace
        )
        interaction.namespace.ephemeral = get_ephemeral(interaction, namespace)  # type: ignore

        transformed_values.pop("private", None)
        return await self._do_call(interaction, transformed_values)

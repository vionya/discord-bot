# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
"""
An auxiliary module for the `Profile` addon
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Any

import discord
import neo

if TYPE_CHECKING:
    from ..profile import Profile


class ChangeSettingButton(discord.ui.Button[neo.ButtonsMenu[neo.EmbedPages]]):
    def __init__(
        self,
        *,
        settings: dict[str, Any],
        addon: Profile,
        ctx: neo.context.NeoContext,
        **kwargs,
    ):
        self.ctx = ctx
        self.addon = addon
        self.settings = settings

        super().__init__(**kwargs)

    async def callback(self, interaction):
        if not self.view:
            return

        index = self.view.current_page
        current_setting = [*self.settings.keys()][index]

        outer_self = self

        class ChangeSettingModal(discord.ui.Modal, title="Edit profile settings"):
            new_value = discord.ui.TextInput(
                label=f"Changing {current_setting}",
                placeholder="New value",
                min_length=1,
                max_length=500,
            )

            async def on_submit(self, interaction):
                if not outer_self.view:
                    return

                try:
                    if self.new_value.value:
                        await outer_self.addon.set_option(
                            outer_self.ctx, current_setting, self.new_value.value
                        )
                except Exception as e:
                    await interaction.response.send_message(e, ephemeral=True)
                else:
                    await interaction.response.send_message(
                        f"Setting `{current_setting}` has been changed!", ephemeral=True
                    )

                    description = outer_self.settings[current_setting][
                        "description"
                    ].format(
                        getattr(
                            outer_self.addon.bot.profiles[outer_self.ctx.author.id],
                            current_setting,
                        )
                    )
                    outer_self.view.pages.items[index].description = (
                        f"**Setting: `{current_setting}`**\n\n" + description
                    )
                    await outer_self.view.refresh_page()

        modal = ChangeSettingModal()

        await interaction.response.send_modal(modal)


class ResetSettingButton(discord.ui.Button[neo.ButtonsMenu[neo.EmbedPages]]):
    def __init__(
        self,
        *,
        settings: dict[str, Any],
        addon: Profile,
        ctx: neo.context.NeoContext,
        **kwargs,
    ):
        self.ctx = ctx
        self.addon = addon
        self.settings = settings

        super().__init__(**kwargs)

    async def callback(self, interaction):
        if not self.ctx.guild or not self.view:
            return

        index = self.view.current_page
        current_setting = [*self.settings.keys()][index]

        await self.addon.reset_option(self.ctx, current_setting)

        await interaction.response.send_message(
            f"Setting `{current_setting}` has been reset!", ephemeral=True
        )

        description = self.settings[current_setting]["description"].format(
            getattr(self.addon.bot.profiles[self.ctx.author.id], current_setting)
        )
        self.view.pages.items[index].description = (
            f"**Setting: `{current_setting}`**\n\n" + description
        )
        await self.view.refresh_page()

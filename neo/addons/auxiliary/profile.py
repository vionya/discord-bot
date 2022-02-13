# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
"""
An auxiliary module for the `Profile` addon
"""
from typing import Any

import discord
import neo


class ChangeSettingButton(discord.ui.Button[neo.ButtonsMenu]):
    def __init__(
        self,
        *,
        settings: dict[str, Any],
        addon: neo.Addon,
        ctx: neo.context.NeoContext,
        **kwargs
    ):
        self.ctx = ctx
        self.addon = addon
        self.settings = settings

        super().__init__(**kwargs)

    async def callback(self, interaction):
        index = self.view.current_page
        current_setting = [*self.settings.keys()][index]

        class ChangeSettingModal(discord.ui.Modal):
            async def on_submit(modal_self, interaction):
                new_value = modal_self.children[0].value

                try:
                    await self.addon.set_option(self.ctx, current_setting, new_value)
                except Exception as e:
                    await interaction.response.send_message(e, ephemeral=True)
                else:
                    await interaction.response.send_message(
                        f"Setting `{current_setting}` has been changed!",
                        ephemeral=True
                    )

                    description = self.settings[current_setting]["description"].format(
                        getattr(self.addon.bot.profiles[self.ctx.author.id], current_setting)
                    )
                    self.view.pages.items[index].description = \
                        f"**Setting: `{current_setting}`**\n\n" + description
                    await self.view.refresh_page()

        modal = ChangeSettingModal(title="Edit profile settings")
        modal.add_item(discord.ui.TextInput(
            label=f"Changing {current_setting}",
            placeholder="New value",
            min_length=1,
            max_length=500
        ))

        await interaction.response.create_modal(modal)


class ResetSettingButton(discord.ui.Button[neo.ButtonsMenu]):
    def __init__(
        self,
        *,
        settings: dict[str, Any],
        addon: neo.Addon,
        ctx: neo.context.NeoContext,
        **kwargs
    ):
        self.ctx = ctx
        self.addon = addon
        self.settings = settings

        super().__init__(**kwargs)

    async def callback(self, interaction):
        index = self.view.current_page
        current_setting = [*self.settings.keys()][index]

        await self.addon.reset_option(self.ctx, current_setting)

        await interaction.response.send_message(
            f"Setting `{current_setting}` has been reset!",
            ephemeral=True
        )

        description = self.settings[current_setting]["description"].format(
            getattr(self.addon.bot.profiles[self.ctx.author.id], current_setting)
        )
        self.view.pages.items[index].description = \
            f"**Setting: `{current_setting}`**\n\n" + description
        await self.view.refresh_page()

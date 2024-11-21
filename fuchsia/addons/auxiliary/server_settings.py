# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 vionya
"""
An auxiliary module for the `ServerSettings` addon
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord

import fuchsia
from fuchsia.classes.containers import Setting, SettingsMapping
from fuchsia.classes.transformers import bool_transformer

if TYPE_CHECKING:
    from ..server_settings import ServerConfig

SETTINGS_MAPPING = SettingsMapping(
    Setting(
        "starboard",
        transformer=bool_transformer,
        name_override="Enable Starboard",
    ),
    Setting("allow_highlights", transformer=bool_transformer),
)


class ChangeSettingButton(discord.ui.Button[fuchsia.ButtonsMenu[fuchsia.EmbedPages]]):
    def __init__(self, *, addon: ServerConfig, **kwargs):
        self.addon = addon

        super().__init__(**kwargs)

    async def callback(self, interaction):
        if not self.view:
            return

        index = self.view.page_index
        current_setting = [*SETTINGS_MAPPING.values()][index]

        outer_self = self

        class ChangeSettingModal(
            discord.ui.Modal, title="Edit server settings"
        ):
            new_value = discord.ui.TextInput(
                label=f"Changing {current_setting.display_name}",
                placeholder="New value",
                min_length=1,
                max_length=500,
            )

            async def on_submit(self, interaction):
                if not interaction.guild or not outer_self.view:
                    return

                try:
                    if self.new_value.value:
                        await outer_self.addon.set_option(
                            interaction,
                            current_setting.key,
                            self.new_value.value,
                        )
                except Exception as e:
                    await interaction.response.send_message(e, ephemeral=True)
                else:
                    await interaction.response.send_message(
                        "Your settings have been updated!", ephemeral=True
                    )

                    description = SETTINGS_MAPPING[current_setting.key][
                        "description"
                    ].format(
                        getattr(
                            outer_self.addon.bot.configs[interaction.guild.id],
                            current_setting.key,
                        )
                    )
                    outer_self.view.pages.items[index].description = (
                        f"**Setting: `{current_setting.display_name}`**\n\n"
                        + description
                    )
                    await outer_self.view.refresh_page()

        modal = ChangeSettingModal()

        await interaction.response.send_modal(modal)


class ResetSettingButton(discord.ui.Button[fuchsia.ButtonsMenu[fuchsia.EmbedPages]]):
    def __init__(self, *, addon: ServerConfig, **kwargs):
        self.addon = addon

        super().__init__(**kwargs)

    async def callback(self, interaction):
        if not interaction.guild or not self.view:
            return

        index = self.view.page_index
        current_setting = [*SETTINGS_MAPPING.values()][index]

        await self.addon.reset_option(interaction, current_setting.key)

        await interaction.response.send_message(
            "Your settings have been updated!", ephemeral=True
        )

        description = SETTINGS_MAPPING[current_setting.key][
            "description"
        ].format(
            getattr(
                self.addon.bot.configs[interaction.guild.id],
                current_setting.key,
            )
        )
        self.view.pages.items[index].description = (
            f"**Setting: `{current_setting.display_name}`**\n\n" + description
        )
        await self.view.refresh_page()

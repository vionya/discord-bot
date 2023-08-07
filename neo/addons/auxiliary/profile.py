# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
"""
An auxiliary module for the `Profile` addon
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord

import neo
from neo.classes.containers import Setting, SettingsMapping
from neo.classes.transformers import (
    bool_transformer,
    timeout_transformer,
    timezone_transformer,
)

if TYPE_CHECKING:
    from ..profile import Profile

SETTINGS_MAPPING = SettingsMapping(
    Setting("receive_highlights", transformer=bool_transformer),
    Setting("timezone", transformer=timezone_transformer),
    Setting(
        "hl_timeout",
        transformer=timeout_transformer,
        name_override="Highlight Timeout",
    ),
    Setting(
        "default_ephemeral",
        transformer=bool_transformer,
        name_override="Private By Default",
    ),
    Setting(
        "silence_hl",
        transformer=bool_transformer,
        name_override="Deliver Highlights Silently",
    ),
    Setting(
        "reminders_in_channel",
        transformer=bool_transformer,
        name_override="Send Reminders Where Created",
    ),
)


class ChangeSettingButton(discord.ui.Button[neo.ButtonsMenu[neo.EmbedPages]]):
    def __init__(self, *, addon: Profile, **kwargs):
        self.addon = addon

        super().__init__(**kwargs)

    async def callback(self, interaction):
        if not self.view:
            return

        index = self.view.page_index
        current_setting = [*SETTINGS_MAPPING.values()][index]

        outer_self = self

        class ChangeSettingModal(
            discord.ui.Modal, title="Edit profile settings"
        ):
            new_value = discord.ui.TextInput(
                label=f"Changing {current_setting.display_name}",
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
                            outer_self.addon.bot.profiles[interaction.user.id],
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


class ResetSettingButton(discord.ui.Button[neo.ButtonsMenu[neo.EmbedPages]]):
    def __init__(self, *, addon: Profile, **kwargs):
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
                self.addon.bot.profiles[interaction.user.id],
                current_setting.key,
            )
        )
        self.view.pages.items[index].description = (
            f"**Setting: `{current_setting.display_name}`**\n\n" + description
        )
        await self.view.refresh_page()

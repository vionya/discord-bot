# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
"""
An auxiliary module for the `Starboard` addon
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord

import fuchsia
from fuchsia.classes.containers import Setting, SettingsMapping
from fuchsia.classes.transformers import (
    max_days_transformer,
    text_channel_transformer,
)

if TYPE_CHECKING:
    from ..starboard import StarboardAddon

SETTINGS_MAPPING = SettingsMapping(
    Setting(
        "channel",
        transformer=text_channel_transformer,
        name_override="Starboard Channel",
        autocomplete_func=lambda interaction, _: [
            (f"#{channel}", channel.mention)
            for channel in interaction.guild.text_channels  # type: ignore  # guild_only
        ],
    ),
    Setting(
        "threshold", transformer=int, name_override="Minimum Stars Required"
    ),
    Setting("format", transformer=str, name_override="Starred Message Format"),
    Setting("max_days", transformer=max_days_transformer),
    Setting(
        "emoji",
        transformer=discord.PartialEmoji.from_str,
        name_override="Star Emoji",
    ),
)


class ChangeSettingButton(discord.ui.Button[fuchsia.ButtonsMenu[fuchsia.EmbedPages]]):
    def __init__(self, *, addon: StarboardAddon, **kwargs):
        self.addon = addon

        super().__init__(**kwargs)

    async def callback(self, interaction):
        if not self.view:
            return

        index = self.view.page_index
        current_setting = [*SETTINGS_MAPPING.values()][index]

        outer_self = self

        class ChangeSettingModal(
            discord.ui.Modal, title="Edit starboard settings"
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
                            outer_self.addon.starboards[interaction.guild.id],
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

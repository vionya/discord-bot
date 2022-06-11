# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04

import discord


async def send_confirmation(interaction: discord.Interaction):
    await interaction.response.send_message("\U00002611")

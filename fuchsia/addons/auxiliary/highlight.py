import discord
from discord import ui

from fuchsia.config import Config


class HighlightsV2Item(ui.DynamicItem[ui.Button[ui.LayoutView]], template=""):
    def __init__(self):
        super().__init__(
            ui.Button(
                label="\u2139\uFE0F",
                custom_id="fuchsia:highlights_v2_coachmark",
            )
        )

    @classmethod
    def from_custom_id(
        cls, interaction: discord.Interaction, item: ui.Button, _
    ):
        return cls()

    async def callback(self, interaction: discord.Interaction):
        view = ui.LayoutView()
        view.add_item(
            ui.Container(ui.TextDisplay(Config().get("strings.info.hv2")))
        )
        await interaction.response.send_message(view=view, ephemeral=True)

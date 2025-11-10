# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 vionya
"""
An auxiliary module for the `Utility` addon
"""
from __future__ import annotations

import random
from collections import Counter
from enum import Enum, auto
from typing import TYPE_CHECKING, cast
from datetime import datetime

import discord
from discord import ui
from discord.http import Route, HTTPClient

import fuchsia
from fuchsia.modules.dictionary import (
    StandardDictionaryResponse,
    UrbanDictionaryResponse,
)
from fuchsia.tools.formatters import Table, shorten
from fuchsia.tools.message_helpers import container_view

if TYPE_CHECKING:
    from fuchsia.modules.cse import SearchResult


def result_to_container(query: str, result: SearchResult):
    container = discord.ui.Container(
        ui.TextDisplay(f'-# Results for "{shorten(query, 40)}"'),
        ui.TextDisplay(f"### {result.title}"),
        ui.TextDisplay(f"**{result.url}**"),
    )
    if result.image_url:
        container.add_item(
            ui.MediaGallery().add_item(
                media=result.image_url,
                description=(shorten(result.snippet, 256) if result.snippet else None),
            )
        )
    elif result.snippet:
        container.add_item(ui.TextDisplay(shorten(result.snippet, 2000)))
    return container


def definitions_to_embed(
    resp: StandardDictionaryResponse | UrbanDictionaryResponse,
):
    if isinstance(resp, UrbanDictionaryResponse):
        # iterate over urban responses
        for definition in resp:
            # construct embed
            # n.b. the shorten calls might accidentally cut off a link but lol
            container = discord.ui.Container(
                ui.TextDisplay(f"### {definition.word} (by {definition.author})"),
                ui.TextDisplay(shorten(definition.definition, 4000)),
                ui.TextDisplay("**Example**"),
                ui.TextDisplay(
                    shorten(definition.example, 1000),
                ),
                ui.TextDisplay("**Sourced from Urban Dictionary**"),
                ui.TextDisplay(
                    "[Link]({0}) | \U0001f44d {1} | \U0001f44e {2} | {3}".format(
                        definition.permalink,
                        definition.thumbs_up,
                        definition.thumbs_down,
                        # want timestamp relative
                        discord.utils.format_dt(definition.written_on, style="R"),
                    ),
                ),
            )
            yield container, (definition.word, definition.definition)
    else:
        # this looks really bad but it's really only O(n^2)
        for word in resp.words:
            for meaning in word.meanings[
                :25
            ]:  # Slice at 25 to fit within dropdown limits
                for definition in meaning.definitions:
                    container = discord.ui.Container(
                        ui.TextDisplay(f"### {word.word}: {meaning.part_of_speech}"),
                        ui.TextDisplay(shorten(definition.definition, 4000)),
                    )
                    if definition.synonyms:
                        container.add_item(ui.TextDisplay("**Synonyms**")).add_item(
                            ui.TextDisplay(", ".join(definition.synonyms[:5]))
                        )
                    yield container, (word.word, definition.definition)


def get_browser_links(avatar: discord.Asset):
    formats = ["png", "jpg", "webp"]
    if avatar.is_animated():
        formats.append("gif")

    return " • ".join(
        f"[{fmt}]({avatar.with_format(fmt)})" for fmt in formats  # type: ignore
    )


class InviteDropdown(discord.ui.Select["InviteMenu"]):
    def __init__(self, *args, **kwargs):
        kwargs["custom_id"] = "fuchsia:invite dropdown menu"
        super().__init__(*args, **kwargs)

    async def callback(self, interaction: discord.Interaction):
        if not self.view:
            return

        url = discord.utils.oauth_url(
            self.view.application_id,
            scopes=(
                "bot",
                "applications.commands",
            ),  # extra assurance in case the default changes
            permissions=discord.Permissions(int(self.values[0])),
        )
        await interaction.response.send_message(
            f"[**Click here to invite fuchsia**]({url})", ephemeral=True
        )


class InviteMenu(discord.ui.View):
    def __init__(self, presets: list[dict[str, str]], application_id: int):
        self.application_id = application_id
        super().__init__(timeout=None)
        dropdown = InviteDropdown(placeholder="Choose Invite Preset")
        for preset in presets:
            dropdown.add_option(
                label=preset["name"],
                description=preset["desc"],
                value=preset["value"],
            )
        self.add_item(dropdown)


class InviteButton(discord.ui.Button):
    def __init__(self, *args, view_kwargs: dict, **kwargs):
        kwargs["style"] = discord.ButtonStyle.primary
        kwargs["label"] = "Invite fuchsia"
        kwargs["custom_id"] = "fuchsia:invite button"
        self.view_kwargs = view_kwargs
        super().__init__(*args, **kwargs)

    async def callback(self, interaction: discord.Interaction):
        embed = fuchsia.Embed(
            title="Select a permissions preset below.",
            description="**Managed Role** A role assigned to fuchsia by "
            "Discord automatically. This role cannot be deleted while the "
            "bot is in a server. Consider `No Permissions` to avoid managed roles."
            "\n\n**Everything** This can be used to be selective with permissions by "
            "disabling what you don't want to grant.",
        )
        await interaction.response.send_message(
            embed=embed, ephemeral=True, view=InviteMenu(**self.view_kwargs)
        )


class InfoButtons(discord.ui.View):
    def __init__(
        self,
        privacy_embed: fuchsia.Embed,
        invite_disabled: bool,
        *,
        buttons: list[discord.ui.Button],
        **invite_menu_kwargs,
    ):
        self.privacy_embed = privacy_embed
        super().__init__(timeout=None)
        self.add_item(
            InviteButton(view_kwargs=invite_menu_kwargs, disabled=invite_disabled)
        )
        for button in buttons:
            self.add_item(button)

    @discord.ui.button(
        custom_id="fuchsia:privacy policy", label="Privacy Policy", row=1
    )
    async def callback(self, interaction: discord.Interaction, _):
        await interaction.response.send_message(
            embed=self.privacy_embed, ephemeral=True
        )


class AssetState(Enum):
    USER = auto()
    GUILD = auto()


class AssetsSwapRow(ui.ActionRow):
    state: AssetState
    user_asset: discord.Asset | None
    guild_asset: discord.Asset | None
    asset_name: str

    def __init__(
        self,
        *,
        user_asset: discord.Asset | None,
        guild_asset: discord.Asset | None,
        asset_name: str,
        block_save: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.user_asset = user_asset
        self.guild_asset = guild_asset
        self.asset_name = asset_name
        self.state = AssetState.GUILD if guild_asset is not None else AssetState.USER

        if block_save is True:
            self.save_current_asset.disabled = True

        self.guild_asset_button.label = f"Server {asset_name.title()}"
        self.user_asset_button.label = f"User {asset_name.title()}"

        # remove the button for the asset that doesn't exist and set the other
        # to blurple
        if self.guild_asset is None:
            self.remove_item(self.guild_asset_button)
            self.user_asset_button.style = discord.ButtonStyle.blurple

        if self.user_asset is None:
            self.remove_item(self.user_asset_button)
            self.guild_asset_button.style = discord.ButtonStyle.blurple

    @ui.button(style=discord.ButtonStyle.blurple)
    async def guild_asset_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        assert (
            self.guild_asset is not None
        )  # this button will not exist if this isn't true
        if not interaction.message or self.view is None:
            return

        cast(ui.MediaGallery, self.view.find_item(67)).clear_items().add_item(
            media=self.guild_asset.url
        )
        cast(ui.TextDisplay, self.view.find_item(101)).content = (
            "**View in browser**\n" + get_browser_links(self.guild_asset)
        )
        self.state = AssetState.GUILD
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.style = discord.ButtonStyle.grey
        button.style = discord.ButtonStyle.blurple
        await interaction.response.edit_message(view=self.view)

    @ui.button(style=discord.ButtonStyle.grey)
    async def user_asset_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        assert (
            self.user_asset is not None
        )  # this button will not exist if this isn't true
        if not interaction.message or self.view is None:
            return

        cast(ui.MediaGallery, self.view.find_item(67)).clear_items().add_item(
            media=self.user_asset.url
        )
        cast(ui.TextDisplay, self.view.find_item(101)).content = (
            "**View in browser**\n" + get_browser_links(self.user_asset)
        )
        self.state = AssetState.USER
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.style = discord.ButtonStyle.grey
        button.style = discord.ButtonStyle.blurple
        await interaction.response.edit_message(view=self.view)

    @ui.button(label="💾", style=discord.ButtonStyle.grey)
    async def save_current_asset(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.message or self.view is None:
            return

        avatar: discord.Asset
        match self.state:
            case AssetState.USER:
                assert self.user_asset is not None
                avatar = self.user_asset
            case AssetState.GUILD:
                assert self.guild_asset is not None
                avatar = self.guild_asset

        file = await avatar.to_file()
        cast(ui.MediaGallery, self.view.find_item(67)).clear_items().add_item(
            media=f"attachment://{file.filename}"
        )
        self.view.remove_item(cast(ui.TextDisplay, self.view.find_item(101)))
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        button.style = discord.ButtonStyle.green
        await interaction.response.edit_message(view=self.view, attachments=[file])
        await interaction.followup.send(
            view=container_view(
                f"The selected {self.asset_name.lower()} has been saved in this message for future reference!"
            ),
            ephemeral=True,
        )
        self.view.stop()


class AssetsView(ui.LayoutView):
    user_id: int

    def __init__(
        self,
        user_id: int,
        *,
        user_asset: discord.Asset | None,
        guild_asset: discord.Asset | None,
        asset_name: str,
        header: str,
        block_save: bool = False,
    ):
        if user_asset is None and guild_asset is None:
            raise ValueError("At least one asset must be provided")

        self.user_id = user_id

        super().__init__()
        active_asset = guild_asset if guild_asset is not None else user_asset
        assert active_asset is not None
        container = ui.Container(
            ui.TextDisplay(f"-# {header}"),
            ui.TextDisplay(
                "**View in browser**\n" + get_browser_links(active_asset),
                id=101,
            ),
            ui.MediaGallery(id=67).add_item(media=active_asset.url),
            AssetsSwapRow(
                asset_name=asset_name,
                user_asset=user_asset,
                guild_asset=guild_asset,
                block_save=block_save,
            ),
        )
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        return interaction.user.id == self.user_id


class StickerInfoRow(ui.ActionRow):
    def __init__(
        self,
        sticker: discord.Sticker,
        interaction: discord.Interaction,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.sticker = sticker
        if not all(
            (
                # we need to be in a server to steal a sticker
                interaction.guild is not None,
                # the user should be able to create new stickers
                interaction.permissions.create_expressions,
                # the bot needs permissions to create stickers and manage them
                interaction.app_permissions.create_expressions,
                interaction.app_permissions.manage_expressions,
                # can only steal `GuildSticker`s
                isinstance(sticker, discord.GuildSticker),
            )
        ):
            self.steal.disabled = True

    @discord.ui.button(label="Steal Sticker", style=discord.ButtonStyle.primary)
    async def steal(self, interaction: discord.Interaction, _: discord.ui.Button):
        assert interaction.guild and isinstance(self.sticker, discord.GuildSticker)

        try:
            # try to create the sticker
            new_sticker = await interaction.guild.create_sticker(
                name=self.sticker.name,
                description=self.sticker.description,
                emoji=self.sticker.emoji,
                file=await self.sticker.to_file(),
            )
        except discord.HTTPException as e:
            match e.code:
                # sticker limit reached
                case 30039:
                    return await interaction.response.send_message(
                        view=container_view(
                            "This server has no available sticker slots"
                        ),
                        ephemeral=True,
                    )
                case _:
                    # default response for anything else
                    return await interaction.response.send_message(
                        view=container_view(f"Something went wrong: {e}"),
                        ephemeral=True,
                    )

        # create something nice to show to users once sticker created
        raw_description = (
            f"**Name** {new_sticker.name}",
            f"**ID** {new_sticker.id}",
            f"**Image Format** `{new_sticker.format.name}`",
            f"**Emoji** :{new_sticker.emoji}:",
        )
        container = ui.Container(
            ui.TextDisplay("Sticker has been stolen!"),
            ui.Section(
                "\n".join(raw_description), accessory=ui.Thumbnail(new_sticker.url)
            ),
        )
        view = ui.LayoutView().add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)


def get_choice(options: list[str]) -> tuple[str, str]:
    data = Counter(random.choice(options) for _ in range(1000))
    table = Table()
    table.init_columns("Item", "%")
    for item, hits in data.most_common():
        table.add_row(shorten(item, 19), f"{(hits / 1000) * 100:.1f}%")
    return (data.most_common(1)[0][0], table.display())


async def get_member_message_data(
    http: HTTPClient, guild: discord.Guild, member: discord.Member | None = None
) -> tuple[int, datetime | None, str | None]:
    query = (
        f"/guilds/{guild.id}/messages/search?"
        f"&sort_by=timestamp&min_id=0&sort_order=asc&offset=0&limit=1"
    )
    if member is not None:
        query += f"&author_id={member.id}"
    res = await http.request(Route("GET", query))
    if len(res["messages"]) == 0:
        return 0, None, None
    data = res["messages"][0][0]
    jump = f"https://discord.com/channels/{guild.id}/{data['channel_id']}/{data['id']}"
    return (
        res["total_results"],
        discord.utils.snowflake_time(int(data["id"])),
        jump,
    )

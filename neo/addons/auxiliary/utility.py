# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
"""
An auxiliary module for the `Utility` addon
"""
from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Optional

import discord

import neo

if TYPE_CHECKING:
    from googletrans import Translator


TRANSLATION_DIRECTIVE = re.compile(
    r"((?P<src>[a-zA-Z\*\_]+|auto)->(?P<dest>[a-zA-Z]+))?"
)


def result_to_embed(result):
    embed = neo.Embed(
        title=result.title, description=result.snippet, url=result.url
    )
    embed.set_image(url=result.image_url or "")
    return embed


def definitions_to_embed(word):
    for meaning in word.meanings[
        :25
    ]:  # Slice at 25 to fit within dropdown limits
        for definition in meaning.definitions:
            embed = neo.Embed(
                description=definition.definition,
                title=f"{word.word}: {meaning.part_of_speech}",
            ).add_field(
                name="Synonyms",
                value=", ".join((definition.synonyms or ["No synonyms"])[:5]),
            )
            yield embed


def get_translation_kwargs(content: str) -> tuple[str, dict[str, str]]:
    kwargs = {"dest": "en", "src": "auto"}

    match = TRANSLATION_DIRECTIVE.match(content)
    if match:
        content = content.replace(match[0], "")
        kwargs = match.groupdict()
        if kwargs["src"] in {"*", "_"}:
            kwargs["src"] = "auto"

    return content.casefold().strip(), kwargs


def do_translate(
    translator: Translator,
    content: str,
    *,
    dest: Optional[str],
    src: Optional[str],
):
    try:
        translation = translator.translate(
            content, dest=dest or "en", src=src or "auto"
        )
    except ValueError as e:
        e.args = (f"An {e.args[0]} was provided",)
        raise
    except Exception:
        raise RuntimeError(
            "Something went wrong with translation. Maybe try again later?"
        )
    return translation


async def translate(translator, *args, **kwargs):  # Lazy async wrapper
    return await asyncio.to_thread(do_translate, translator, *args, **kwargs)


def full_timestamp(timestamp: float) -> str:
    """
    Returns a detailed Discord timestamp string

    Timestamps are in the form "<t:xxx:d> <t:xxx:T>"

    :param timestamp: The timestamp to convert to string
    :type timestamp: ``float``

    :return: The Discord-formatted timestamp string
    :rtype: ``str``
    """
    date = f"<t:{timestamp:.0f}:d>"
    time = f"<t:{timestamp:.0f}:T>"
    return date + " " + time


class InviteDropdown(discord.ui.Select["InviteMenu"]):
    def __init__(self, *args, **kwargs):
        kwargs["custom_id"] = "neo phoenix:invite dropdown menu"
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
            f"[**Click here to invite neo phoenix**]({url})", ephemeral=True
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
        kwargs["label"] = "Invite neo phoenix"
        kwargs["custom_id"] = "neo phoenix:invite button"
        self.view_kwargs = view_kwargs
        super().__init__(*args, **kwargs)

    async def callback(self, interaction: discord.Interaction):
        embed = neo.Embed(
            title="Select a permissions preset below.",
            description="**Managed Role** A role assigned to neo phoenix by "
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
        privacy_embed: neo.Embed,
        invite_disabled: bool,
        *,
        buttons: list[discord.ui.Button],
        **invite_menu_kwargs,
    ):
        self.privacy_embed = privacy_embed
        super().__init__(timeout=None)
        self.add_item(
            InviteButton(
                view_kwargs=invite_menu_kwargs, disabled=invite_disabled
            )
        )
        for button in buttons:
            self.add_item(button)

    @discord.ui.button(
        custom_id="neo phoenix:privacy policy", label="Privacy Policy", row=1
    )
    async def callback(self, interaction: discord.Interaction, button):
        await interaction.response.send_message(
            embed=self.privacy_embed, ephemeral=True
        )


class SwappableEmbedButton(discord.ui.Button):
    def __init__(self, *args, **kwargs):
        kwargs["label"] = "Swap image sizes"
        super().__init__(*args, **kwargs)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.message:
            return

        embed = interaction.message.embeds[0]
        image, thumbnail = embed.image, embed.thumbnail
        embed = embed.set_image(url=thumbnail.url).set_thumbnail(url=image.url)
        await interaction.response.defer()
        await interaction.edit_original_response(embed=embed)

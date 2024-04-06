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

import fuchsia
from fuchsia.modules.dictionary import (
    StandardDictionaryResponse,
    UrbanDictionaryResponse,
)
from fuchsia.tools.formatters import shorten

if TYPE_CHECKING:
    from googletrans import Translator

    from fuchsia.modules.cse import SearchResult


TRANSLATION_DIRECTIVE = re.compile(
    r"((?P<src>[a-zA-Z\*\_]+|auto)->(?P<dest>[a-zA-Z]+))?"
)


def result_to_embed(result: SearchResult):
    embed = fuchsia.Embed(title=result.title, url=result.url)
    if result.image_url:
        embed.set_image(url=result.image_url)
    else:
        embed.description = result.snippet
    return embed


def definitions_to_embed(
    resp: StandardDictionaryResponse | UrbanDictionaryResponse,
):
    if isinstance(resp, UrbanDictionaryResponse):
        # iterate over urban responses
        for definition in resp:
            # construct embed
            # n.b. the shorten calls might accidentally cut off a link but lol
            embed = (
                fuchsia.Embed(
                    description=shorten(definition.definition, 4000),
                    title=f"{definition.word} (by {definition.author})",
                )
                .add_field(
                    name="Example",
                    value=shorten(definition.example, 1000),
                    inline=False,
                )
                .add_field(
                    name="Sourced from Urban Dictionary",
                    value="[Link]({0}) | \U0001F44D {1} | \U0001F44E {2} | {3}".format(
                        definition.permalink,
                        definition.thumbs_up,
                        definition.thumbs_down,
                        # want timestamp relative
                        discord.utils.format_dt(
                            definition.written_on, style="R"
                        ),
                    ),
                    inline=False,
                )
            )
            yield embed
    else:
        # this looks really bad but it's really only O(n^2)
        for word in resp.words:
            for meaning in word.meanings[
                :25
            ]:  # Slice at 25 to fit within dropdown limits
                for definition in meaning.definitions:
                    embed = fuchsia.Embed(
                        description=definition.definition,
                        title=f"{word.word}: {meaning.part_of_speech}",
                    )

                    if definition.synonyms:
                        embed.add_field(
                            name="Synonyms",
                            value=", ".join(definition.synonyms[:5]),
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
            InviteButton(
                view_kwargs=invite_menu_kwargs, disabled=invite_disabled
            )
        )
        for button in buttons:
            self.add_item(button)

    @discord.ui.button(
        custom_id="fuchsia:privacy policy", label="Privacy Policy", row=1
    )
    async def callback(self, interaction: discord.Interaction, button):
        await interaction.response.send_message(
            embed=self.privacy_embed, ephemeral=True
        )


class SwappableEmbedButton(discord.ui.Button):
    def __init__(self, *args, **kwargs):
        kwargs["label"] = "Swap image sizes"
        kwargs["style"] = discord.ButtonStyle.primary
        super().__init__(*args, **kwargs)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.message:
            return

        embed = interaction.message.embeds[0]
        image, thumbnail = embed.image, embed.thumbnail
        embed = embed.set_image(url=thumbnail.url).set_thumbnail(url=image.url)
        await interaction.response.defer()
        await interaction.edit_original_response(embed=embed)


class StickerInfoView(discord.ui.View):
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
    async def steal(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        assert interaction.guild and isinstance(
            self.sticker, discord.GuildSticker
        )

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
                        "This server has no available sticker slots",
                        ephemeral=True,
                    )
                case _:
                    # default response for anything else
                    return await interaction.response.send_message(
                        f"Something went wrong: {e}", ephemeral=True
                    )

        # create something nice to show to users once sticker created
        raw_description = (
            f"**Name** {new_sticker.name}",
            f"**ID** {new_sticker.id}",
            f"**Image Format** `{new_sticker.format.name}`",
            f"**Emoji** :{new_sticker.emoji}:",
        )
        embed = fuchsia.Embed(
            title="Sticker has been stolen!",
            description="\n".join(raw_description),
        ).set_thumbnail(url=new_sticker.url)
        await interaction.response.send_message(embeds=[embed], ephemeral=True)

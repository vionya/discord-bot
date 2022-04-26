# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from typing import TypedDict


class NeoInvitePreset(TypedDict):
    name: str
    desc: str
    value: str


class NeoSupport(TypedDict):
    url: str
    disabled: bool


class NeoBotConfig(TypedDict):
    token: str
    cse_keys: list[str]
    cse_engine: str
    prefix: str
    activity_name: str
    activity_type: str
    status: str
    ignored_exceptions: list[str]
    sync_app_commands: bool


class NeoDataBaseConfig:
    user: str
    password: str
    database: str
    host: str


class NeoConfig(TypedDict):
    addons: list[str]
    upstream_url: str
    privacy_policy_path: str
    invite_presets: list[NeoInvitePreset]
    support: NeoSupport

    bot: NeoBotConfig
    database: NeoDataBaseConfig

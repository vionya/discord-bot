# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
from typing import TypedDict


class FuchsiaInvitePreset(TypedDict):
    name: str
    desc: str
    value: str

class FuchsiaInfoLink(TypedDict):
    url: str
    disabled: bool

class FuchsiaBotConfig(TypedDict):
    token: str
    cse_keys: list[str]
    cse_engine: str
    prefix: str
    activity_name: str
    activity_state: str
    activity_type: str
    status: str
    ignored_exceptions: list[str]
    sync_app_commands: bool


class FuchsiaDataBaseConfig(TypedDict):
    user: str
    password: str
    database: str
    host: str


class FuchsiaConfig(TypedDict):
    addons: list[str]
    privacy_policy_path: str
    invite_presets: list[FuchsiaInvitePreset]
    support: FuchsiaInfoLink
    upstream: FuchsiaInfoLink
    api: str

    bot: FuchsiaBotConfig
    database: FuchsiaDataBaseConfig

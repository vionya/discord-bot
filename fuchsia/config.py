# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 vionya
from typing import Any

from fuchsia.classes.singleton import Singleton
from fuchsia.types.config import FuchsiaConfig


class Config(metaclass=Singleton):
    __slots__ = "_config"

    _config: FuchsiaConfig | None

    def __init__(self):
        self._config = None

    def set_config(self, config: FuchsiaConfig):
        self._config = config

    def get_config(self) -> FuchsiaConfig | None:
        return self._config

    def get(self, key: str) -> Any:
        layer = self._config or {}
        for k in key.split("."):
            if k not in layer:
                return None
            layer = layer[k]
        return layer

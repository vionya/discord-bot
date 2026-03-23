# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2020-present vionya

from abc import ABCMeta, abstractmethod
from typing import TypeGuard


class FuchsiaException(Exception):
    """The base class that all fuchsia-related exceptions derive from"""


class SilentFail(FuchsiaException):
    """Silently fail a command. This error is suppressed to the user"""


class UserFacingException(FuchsiaException, metaclass=ABCMeta):
    __is_user_facing__ = True

    @property
    @abstractmethod
    def flavor_text(self) -> str | None:
        raise NotImplemented()


def is_user_facing(exc: BaseException) -> TypeGuard[UserFacingException]:
    return getattr(exc, "__is_user_facing__", False)


class UserValueError(UserFacingException):
    @property
    def flavor_text(self):
        return "There was an issue with your input"


class UserGenericError(UserFacingException):
    @property
    def flavor_text(self):
        return None


class UserLimitError(UserFacingException):
    @property
    def flavor_text(self):
        return "You've reached your limit for a resource"

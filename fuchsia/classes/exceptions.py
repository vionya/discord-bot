# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
class FuchsiaException(Exception):
    """The base class that all fuchsia-related exceptions derive from"""

class SilentFail(FuchsiaException):
    """Silently fail a command. This error is suppressed to the user"""
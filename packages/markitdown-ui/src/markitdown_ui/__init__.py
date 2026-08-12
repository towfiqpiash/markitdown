# SPDX-FileCopyrightText: 2024-present Adam Fourney <adamfo@microsoft.com>
#
# SPDX-License-Identifier: MIT
from .__about__ import __version__
from .app import app, create_app

__all__ = ["app", "create_app", "__version__"]

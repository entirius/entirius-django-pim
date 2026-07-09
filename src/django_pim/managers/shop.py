# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Backward-compatible shim — canonical definitions live in channel.py
from .channel import ChannelManager, ShopManager

__all__ = ["ChannelManager", "ShopManager"]

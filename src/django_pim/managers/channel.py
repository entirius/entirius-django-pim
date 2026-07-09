# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from ..models import Channel

logger = logging.getLogger(__name__)


class ChannelManager:
    _cache_channels = {}

    def print_available_ids():
        channels = Channel.objects.all()
        print("Available PIM Channels ids:")
        for channel in channels:
            print(f"  - {channel.idx}")
        print("", flush=True)

    def get_channel(idx):
        if idx not in ChannelManager._cache_channels:
            ChannelManager._cache_channels[idx] = Channel.objects.get(idx=idx)
        return ChannelManager._cache_channels[idx]

    def get_or_create_channel(idx, name=None):
        if idx in ChannelManager._cache_channels:
            return ChannelManager._cache_channels[idx], False

        channel = Channel.objects.filter(idx=idx).first()
        if channel is None:
            created = True
            channel = Channel(idx=idx, name=name)
            channel.save()
            logger.info("New Channel: [%s]", idx)
        else:
            created = False
            ChannelManager.update_channel(channel=channel, name=name)
        ChannelManager._cache_channels[idx] = channel
        return (channel, created)

    def update_channel(channel, name=None):
        updated = []
        to_save = False
        if name is not None and channel.name != name:
            channel.name = name
            updated.append("name")
            to_save = True
        if to_save:
            channel.save()
            logger.info("Channel [%s] updated fields: (%s)", channel.idx, ", ".join(updated))


# Backward-compatible aliases
ShopManager = ChannelManager

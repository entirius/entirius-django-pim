# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Channel service layer for business logic."""

from django.db.models import QuerySet

from ..models import Channel

# Maps API ordering params to actual DB field paths.
ORDERING_MAP: dict[str, str] = {
    "name": "name",
    "-name": "-name",
    "idx": "idx",
    "-idx": "-idx",
}


def list_channels(search: str | None = None, ordering: str | None = None) -> QuerySet[Channel]:
    """
    List channels with optional filtering.

    Args:
        search: Search term for name filtering (case-insensitive)
        ordering: Field to order by (default: name)
    """
    qs = Channel.objects.select_related("default_language", "default_currency").prefetch_related("languages").all()

    if search:
        qs = qs.filter(name__icontains=search)

    order_field = ORDERING_MAP.get(ordering, "name") if ordering else "name"
    qs = qs.order_by(order_field)

    return qs


def get_channel_language(channel_idx: str | None) -> str | None:
    """Get the default language ISO2 code for a channel.

    Returns None if channel_idx is falsy or channel does not exist.
    """
    if not channel_idx:
        return None
    try:
        ch = Channel.objects.select_related("default_language").get(idx=channel_idx)
        return ch.default_language.iso2.lower()
    except Channel.DoesNotExist:
        return None


def get_default_channel() -> Channel | None:
    """Get the default channel. Returns None if none configured."""
    return (
        Channel.objects.select_related("default_language", "default_currency")
        .prefetch_related("languages")
        .filter(is_default=True)
        .first()
    )


def set_default_channel(channel_idx: str) -> Channel:
    """Atomically switch which channel is the default.

    Args:
        channel_idx: The idx of the channel to make default.

    Raises:
        Channel.DoesNotExist: If no channel with that idx exists.
    """
    channel = Channel.objects.get(idx=channel_idx)
    channel.is_default = True
    channel.save()  # save() handles un-defaulting the previous one atomically
    return channel

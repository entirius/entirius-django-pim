# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for channel_service — list, get_default, set_default, get_channel_language."""

import pytest

from django_pim.services.channel_service import (
    get_channel_language,
    get_default_channel,
    list_channels,
    set_default_channel,
)

from .factories import ChannelFactory


@pytest.mark.django_db
class TestListChannels:
    def test_returns_all_channels(self):
        c1 = ChannelFactory(name="Alpha")
        c2 = ChannelFactory(name="Beta")
        result = list(list_channels())
        assert len(result) == 2

    def test_search_filters_by_name(self):
        ChannelFactory(name="Europe Store")
        ChannelFactory(name="Asia Store")
        result = list(list_channels(search="europe"))
        assert len(result) == 1
        assert result[0].name == "Europe Store"

    def test_ordering_by_name(self):
        ChannelFactory(name="Zebra")
        ChannelFactory(name="Alpha")
        result = list(list_channels(ordering="name"))
        assert result[0].name == "Alpha"
        assert result[1].name == "Zebra"

    def test_ordering_descending(self):
        ChannelFactory(name="Zebra")
        ChannelFactory(name="Alpha")
        result = list(list_channels(ordering="-name"))
        assert result[0].name == "Zebra"

    def test_invalid_ordering_falls_back_to_default(self):
        ChannelFactory(name="Alpha")
        ChannelFactory(name="Beta")
        result = list(list_channels(ordering="evil__field"))
        assert len(result) == 2  # no crash, fallback to "name"
        assert result[0].name == "Alpha"


@pytest.mark.django_db
class TestGetDefaultChannel:
    def test_returns_none_when_no_default(self):
        ChannelFactory(is_default=False)
        assert get_default_channel() is None

    def test_returns_default_channel(self):
        ch = ChannelFactory(is_default=True)
        result = get_default_channel()
        assert result.pk == ch.pk
        assert result.is_default is True


@pytest.mark.django_db
class TestSetDefaultChannel:
    def test_sets_channel_as_default(self):
        ch = ChannelFactory(is_default=False)
        result = set_default_channel(ch.idx)
        result.refresh_from_db()
        assert result.is_default is True

    def test_raises_on_nonexistent_channel(self):
        from django_pim.models import Channel

        with pytest.raises(Channel.DoesNotExist):
            set_default_channel("nonexistent-channel")

    def test_switching_default_unsets_previous(self):
        ch1 = ChannelFactory(is_default=True)
        ch2 = ChannelFactory(is_default=False)
        set_default_channel(ch2.idx)
        ch1.refresh_from_db()
        ch2.refresh_from_db()
        assert ch1.is_default is False
        assert ch2.is_default is True


@pytest.mark.django_db
class TestGetChannelLanguage:
    def test_returns_none_for_none_idx(self):
        assert get_channel_language(None) is None

    def test_returns_none_for_empty_string(self):
        assert get_channel_language("") is None

    def test_returns_none_for_nonexistent_channel(self):
        assert get_channel_language("ghost-channel") is None

    def test_returns_language_iso2(self):
        ch = ChannelFactory()
        result = get_channel_language(ch.idx)
        assert result == ch.default_language.iso2.lower()

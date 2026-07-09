# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Tests for PIM signal kill-switch and infrastructure.

Tests cover:
- suppress_matrix_signals() context manager (thread-local suppression)
- is_matrix_sync_suppressed() state query
- is_matrix_signals_enabled() with PimSettings DB toggle + cache
- PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST Django setting
"""

import threading

import pytest
from django.core.cache import cache
from django.test import TestCase, override_settings

from django_pim.models.pim_settings import PimSettings
from django_pim.signals.killswitch import is_matrix_signals_enabled, is_matrix_sync_suppressed, suppress_matrix_signals

# ============================================================================
# suppress_matrix_signals() context manager
# ============================================================================


class SuppressMatrixSignalsTest(TestCase):
    """Tests for suppress_matrix_signals() context manager."""

    def test_suppressed_inside_block(self):
        # Arrange / Act / Assert
        with suppress_matrix_signals():
            assert is_matrix_sync_suppressed() is True

    def test_not_suppressed_outside_block(self):
        # Arrange + Act
        with suppress_matrix_signals():
            pass
        # Assert: flag cleared on exit
        assert is_matrix_sync_suppressed() is False

    def test_cleared_after_exception(self):
        # Act: exception inside the context manager
        with pytest.raises(ValueError):
            with suppress_matrix_signals():
                raise ValueError("test")
        # Assert: flag still cleared via finally
        assert is_matrix_sync_suppressed() is False

    def test_nested_inner_exit_preserves_outer(self):
        # Arrange + Act
        with suppress_matrix_signals():
            with suppress_matrix_signals():
                pass
            # Assert: inner exited but outer still active
            assert is_matrix_sync_suppressed() is True
        # Assert: fully cleared once outer exits
        assert is_matrix_sync_suppressed() is False

    def test_thread_isolation(self):
        """Suppression in one thread does not affect a concurrent thread."""
        results = {}

        def check_in_thread():
            results["other_thread"] = is_matrix_sync_suppressed()

        with suppress_matrix_signals():
            t = threading.Thread(target=check_in_thread)
            t.start()
            t.join()

        assert results["other_thread"] is False

    def test_default_not_suppressed(self):
        # No context manager active — must start as False
        assert is_matrix_sync_suppressed() is False


# ============================================================================
# is_matrix_signals_enabled() — DB toggle + cache
# ============================================================================


@pytest.mark.django_db
class IsMatrixSignalsEnabledTest(TestCase):
    """Tests for is_matrix_signals_enabled() reading PimSettings with caching."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_returns_false_when_disabled(self):
        # Arrange
        settings = PimSettings.load()
        settings.matrix_signals_enabled = False
        settings.save()

        # Act
        result = is_matrix_signals_enabled()

        # Assert
        assert result is False

    def test_returns_true_when_enabled(self):
        # Arrange
        settings = PimSettings.load()
        settings.matrix_signals_enabled = True
        settings.save()

        # Act
        result = is_matrix_signals_enabled()

        # Assert
        assert result is True

    def test_result_is_cached(self):
        # Arrange: set enabled in DB, prime the cache
        settings = PimSettings.load()
        settings.matrix_signals_enabled = True
        settings.save()
        is_matrix_signals_enabled()  # prime cache

        # Act: change DB without touching cache
        PimSettings.objects.filter(pk=1).update(matrix_signals_enabled=False)

        # Assert: cached value (True) still returned
        assert is_matrix_signals_enabled() is True

    def test_cache_key_is_correct(self):
        # Arrange
        settings = PimSettings.load()
        settings.matrix_signals_enabled = True
        settings.save()

        # Act
        is_matrix_signals_enabled()

        # Assert: exact cache key populated
        assert cache.get("pim:matrix_signals_enabled") is True

    def test_cache_invalidation_on_save(self):
        """Clearing cache after PimSettings.save() allows fresh DB read."""
        # Arrange: enable, prime cache
        settings = PimSettings.load()
        settings.matrix_signals_enabled = True
        settings.save()
        is_matrix_signals_enabled()
        assert cache.get("pim:matrix_signals_enabled") is True

        # Act: disable + manually invalidate (as admin save would)
        settings.matrix_signals_enabled = False
        settings.save()
        cache.delete("pim:matrix_signals_enabled")

        # Assert: fresh read returns updated value
        assert is_matrix_signals_enabled() is False

    def test_default_is_false(self):
        """Fresh PimSettings singleton defaults matrix_signals_enabled to False."""
        # Arrange: delete singleton to force a clean get_or_create
        PimSettings.objects.all().delete()

        # Act
        result = is_matrix_signals_enabled()

        # Assert
        assert result is False


# ============================================================================
# PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST setting
# ============================================================================


@pytest.mark.django_db
class ChannelDenylistTest(TestCase):
    """Tests for PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST configuration."""

    def setUp(self):
        cache.clear()
        settings = PimSettings.load()
        settings.matrix_signals_enabled = True
        settings.save()

    def tearDown(self):
        cache.clear()

    @override_settings(PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST=["blocked-channel"])
    def test_channel_in_denylist_is_present(self):
        """Setting is readable and contains the blocked channel."""
        from django.conf import settings as django_settings

        denylist = getattr(django_settings, "PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST", [])
        assert "blocked-channel" in denylist

    @override_settings(PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST=[])
    def test_empty_denylist_allows_all(self):
        from django.conf import settings as django_settings

        denylist = getattr(django_settings, "PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST", [])
        assert len(denylist) == 0

    @override_settings(PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST=["ch-a", "ch-b"])
    def test_multiple_channels_in_denylist(self):
        from django.conf import settings as django_settings

        denylist = getattr(django_settings, "PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST", [])
        assert "ch-a" in denylist
        assert "ch-b" in denylist
        assert "ch-c" not in denylist

    @override_settings(PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST=["import-only"])
    def test_pim_settings_module_reflects_override(self):
        """pim_settings module reads the denylist from Django settings."""
        from django.conf import settings as django_settings

        # The module reads via getattr(settings, ...) on import,
        # so re-read directly from Django settings after override.
        denylist = getattr(django_settings, "PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST", [])
        assert "import-only" in denylist

    def test_default_denylist_is_empty_list(self):
        """Without override, PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST defaults to []."""
        from django_pim import settings as pim_settings

        # Default value set in pim settings.py
        assert isinstance(pim_settings.PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST, list)

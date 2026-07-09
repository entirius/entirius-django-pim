# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Tests for the PIM signal dispatch (debounce) layer.

Tests cover:
- enqueue_product_sync() Redis sorted-set operations
- SETNX-based flush scheduling (deduplicated flush task)
- Debounce countdown uses PIM_MATRIX_SIGNALS_DEBOUNCE_SECONDS
- TTL is applied to the pending set key
- Graceful degradation when Redis is unavailable
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase


def _make_redis_mock(setnx_returns=False):
    """Return a configured Redis client mock."""
    redis_mock = MagicMock()
    redis_mock.set.return_value = setnx_returns
    return redis_mock


def _patch_caches(redis_mock):
    """Return a patcher that injects redis_mock into caches['default']."""
    cache_mock = MagicMock()
    cache_mock.__getitem__.return_value.client.get_client.return_value = redis_mock
    return patch("django_pim.signals.dispatch.caches", cache_mock)


# ============================================================================
# Redis sorted-set operations
# ============================================================================


class EnqueueProductSyncRedisOpsTest(TestCase):
    """enqueue_product_sync() writes to the correct Redis key and member."""

    def _call(self, sku, channel):
        from django_pim.signals.dispatch import enqueue_product_sync

        enqueue_product_sync(sku, channel)

    def test_adds_member_to_pending_sorted_set(self):
        # Arrange
        redis_mock = _make_redis_mock()
        with _patch_caches(redis_mock):
            # Act
            self._call("SKU-001", "default-europe")

        # Assert: zadd called with correct key
        redis_mock.zadd.assert_called_once()
        key = redis_mock.zadd.call_args[0][0]
        assert key == "pim:matrix:pending"

    def test_member_is_sku_colon_channel(self):
        # Arrange
        redis_mock = _make_redis_mock()
        with _patch_caches(redis_mock):
            self._call("SKU-001", "default-europe")

        member_dict = redis_mock.zadd.call_args[0][1]
        assert "SKU-001:default-europe" in member_dict

    def test_multiple_skus_each_call_zadd(self):
        # Arrange
        redis_mock = _make_redis_mock()
        with _patch_caches(redis_mock):
            self._call("SKU-001", "ch-a")
            self._call("SKU-002", "ch-a")

        assert redis_mock.zadd.call_count == 2

    def test_same_sku_channel_calls_zadd_both_times(self):
        """Both calls go through — Redis set handles de-duplication server-side."""
        redis_mock = _make_redis_mock()
        with _patch_caches(redis_mock):
            self._call("SKU-001", "ch-a")
            self._call("SKU-001", "ch-a")

        assert redis_mock.zadd.call_count == 2
        for c in redis_mock.zadd.call_args_list:
            assert "SKU-001:ch-a" in c[0][1]

    def test_different_channels_produce_separate_members(self):
        # Arrange
        redis_mock = _make_redis_mock()
        with _patch_caches(redis_mock):
            self._call("SKU-001", "ch-a")
            self._call("SKU-001", "ch-b")

        members = [list(c[0][1].keys())[0] for c in redis_mock.zadd.call_args_list]
        assert "SKU-001:ch-a" in members
        assert "SKU-001:ch-b" in members


# ============================================================================
# TTL on pending set
# ============================================================================


class EnqueueProductSyncTtlTest(TestCase):
    """Pending sorted-set receives a TTL after each enqueue."""

    def _call(self, sku="SKU-001", channel="ch-a"):
        from django_pim.signals.dispatch import enqueue_product_sync

        enqueue_product_sync(sku, channel)

    def test_sets_pending_key_ttl_to_300(self):
        # Arrange
        redis_mock = _make_redis_mock()
        with _patch_caches(redis_mock):
            self._call()

        redis_mock.expire.assert_called_once_with("pim:matrix:pending", 300)


# ============================================================================
# Flush scheduling via SETNX
# ============================================================================


class EnqueueProductSyncFlushSchedulingTest(TestCase):
    """Flush task is scheduled once via SETNX; subsequent calls skip it."""

    def _call(self, sku="SKU-001", channel="ch-a"):
        from django_pim.signals.dispatch import enqueue_product_sync

        enqueue_product_sync(sku, channel)

    def test_setnx_success_schedules_flush_task(self):
        # Arrange: SETNX returns True (lock acquired)
        redis_mock = _make_redis_mock(setnx_returns=True)
        with _patch_caches(redis_mock), patch("django_pim.signals.dispatch.current_app") as mock_celery:
            self._call()

        mock_celery.send_task.assert_called_once_with(
            "django_matrix.tasks.flush_pending_matrix_sync", countdown=5, queue="matrix_pull"
        )

    def test_setnx_failure_skips_flush_task(self):
        # Arrange: SETNX returns False (lock already held)
        redis_mock = _make_redis_mock(setnx_returns=False)
        with _patch_caches(redis_mock), patch("django_pim.signals.dispatch.current_app") as mock_celery:
            self._call()

        mock_celery.send_task.assert_not_called()

    def test_flush_dispatched_to_matrix_pull_queue(self):
        # Arrange
        redis_mock = _make_redis_mock(setnx_returns=True)
        with _patch_caches(redis_mock), patch("django_pim.signals.dispatch.current_app") as mock_celery:
            self._call()

        kwargs = mock_celery.send_task.call_args[1]
        assert kwargs.get("queue") == "matrix_pull"

    def test_flush_countdown_matches_default_debounce(self):
        # Arrange
        redis_mock = _make_redis_mock(setnx_returns=True)
        with _patch_caches(redis_mock), patch("django_pim.signals.dispatch.current_app") as mock_celery:
            self._call()

        kwargs = mock_celery.send_task.call_args[1]
        assert kwargs.get("countdown") == 5


# ============================================================================
# Debounce setting
# ============================================================================


class EnqueueProductSyncDebounceTest(TestCase):
    """PIM_MATRIX_SIGNALS_DEBOUNCE_SECONDS controls the countdown."""

    def test_uses_custom_debounce_setting(self):
        # Arrange
        redis_mock = _make_redis_mock(setnx_returns=True)
        with (
            _patch_caches(redis_mock),
            patch("django_pim.signals.dispatch.pim_settings") as mock_settings,
            patch("django_pim.signals.dispatch.current_app") as mock_celery,
        ):
            mock_settings.PIM_MATRIX_SIGNALS_DEBOUNCE_SECONDS = 10

            from django_pim.signals.dispatch import enqueue_product_sync

            enqueue_product_sync("SKU-001", "ch-a")

        kwargs = mock_celery.send_task.call_args[1]
        assert kwargs.get("countdown") == 10

    def test_default_debounce_is_five_seconds(self):
        from django_pim import settings as pim_settings

        assert pim_settings.PIM_MATRIX_SIGNALS_DEBOUNCE_SECONDS == 5


# ============================================================================
# Graceful degradation — Redis errors
# ============================================================================


class EnqueueProductSyncErrorHandlingTest(TestCase):
    """Redis failures produce warnings and do not propagate exceptions."""

    def _call(self, sku="SKU-001", channel="ch-a"):
        from django_pim.signals.dispatch import enqueue_product_sync

        enqueue_product_sync(sku, channel)

    def test_redis_connection_error_logs_warning(self):
        # Arrange: caches raises on access
        with patch("django_pim.signals.dispatch.caches") as mock_caches:
            mock_caches.__getitem__.side_effect = Exception("Connection refused")

            with self.assertLogs("django_pim.signals", level="WARNING") as log:
                self._call()

        assert any("Redis unavailable" in msg for msg in log.output)

    def test_redis_connection_error_does_not_raise(self):
        # enqueue_product_sync must never propagate Redis errors to callers
        with patch("django_pim.signals.dispatch.caches") as mock_caches:
            mock_caches.__getitem__.side_effect = Exception("Connection refused")

            # Should complete without raising
            self._call()

    def test_redis_zadd_error_logs_warning(self):
        # Arrange: zadd raises
        redis_mock = _make_redis_mock()
        redis_mock.zadd.side_effect = Exception("Redis timeout")
        with _patch_caches(redis_mock):
            with self.assertLogs("django_pim.signals", level="WARNING") as log:
                self._call()

        assert any("Redis error" in msg for msg in log.output)

    def test_redis_zadd_error_does_not_raise(self):
        redis_mock = _make_redis_mock()
        redis_mock.zadd.side_effect = Exception("Redis timeout")
        with _patch_caches(redis_mock):
            # Should complete without raising
            self._call()

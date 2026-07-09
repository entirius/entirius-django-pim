# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Tests for Phase 6F: Signal infrastructure performance benchmarks.

Tests verify that the signal kill-switch and context manager overhead stay
within acceptable latency budgets so they cannot noticeably slow request paths.

F.I.R.S.T. note: these tests are inherently timing-sensitive. Limits are set
conservatively (10-100x above expected values) to avoid flakiness on slow CI
runners while still catching catastrophic regressions.
"""

import time
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import TestCase

from django_pim.models.pim_settings import PimSettings
from django_pim.signals.killswitch import is_matrix_signals_enabled, suppress_matrix_signals


def _enable_signals() -> None:
    settings = PimSettings.load()
    settings.matrix_signals_enabled = True
    settings.save()
    cache.delete("pim:matrix_signals_enabled")


# ---------------------------------------------------------------------------
# Kill-switch cache performance
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.django_db
class CacheHitPerformanceTest(TestCase):
    """is_matrix_signals_enabled() with a warm cache must be fast."""

    def setUp(self):
        cache.clear()
        _enable_signals()
        # Warm the cache with one call
        is_matrix_signals_enabled()

    def tearDown(self):
        cache.clear()

    def test_cache_hit_average_under_1ms(self):
        """Warm-cache lookups must average < 1 ms over 1000 iterations."""
        iterations = 1000

        start = time.perf_counter()
        for _ in range(iterations):
            is_matrix_signals_enabled()
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        assert avg_ms < 1.0, f"Average cache-hit time {avg_ms:.4f}ms exceeds 1ms"

    def test_cache_hit_total_1000_calls_under_500ms(self):
        """1000 consecutive cached lookups must complete in under 500 ms total."""
        iterations = 1000

        start = time.perf_counter()
        for _ in range(iterations):
            is_matrix_signals_enabled()
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 500, f"1000 cache-hit calls took {elapsed_ms:.1f}ms, expected < 500ms"


# ---------------------------------------------------------------------------
# Context manager overhead
# ---------------------------------------------------------------------------


@pytest.mark.slow
class SuppressContextManagerPerformanceTest(TestCase):
    """suppress_matrix_signals() entry/exit must have negligible overhead."""

    def test_context_manager_average_overhead_under_0_1ms(self):
        """10 000 empty context-manager invocations must average < 0.1 ms each."""
        iterations = 10_000

        start = time.perf_counter()
        for _ in range(iterations):
            with suppress_matrix_signals():
                pass
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        assert avg_ms < 0.1, f"Average context-manager overhead {avg_ms:.4f}ms exceeds 0.1ms"

    def test_nested_context_managers_still_fast(self):
        """Two-deep nesting must still complete 1000 pairs in under 200 ms total."""
        iterations = 1000

        start = time.perf_counter()
        for _ in range(iterations):
            with suppress_matrix_signals():
                with suppress_matrix_signals():
                    pass
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 200, f"1000 nested context-manager pairs took {elapsed_ms:.1f}ms, expected < 200ms"


# ---------------------------------------------------------------------------
# Signal handler overhead (mocked enqueue)
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.django_db
class SignalHandlerOverheadTest(TestCase):
    """Signal handler path must not add significant latency to model saves."""

    def setUp(self):
        cache.clear()
        _enable_signals()
        # Warm the kill-switch cache
        is_matrix_signals_enabled()

    def tearDown(self):
        cache.clear()

    @patch("django_pim.signals.handlers.enqueue_product_sync")
    def test_signal_handler_average_under_50ms_per_save(self, mock_enqueue):
        """Model saves with signals enabled must average < 50 ms (DB included)."""
        from tests.factories import ProductFactory

        # Create a product to warm DB connections; reset mock after
        product = ProductFactory()
        mock_enqueue.reset_mock()

        iterations = 30

        start = time.perf_counter()
        for i in range(iterations):
            product.is_enabled = i % 2 == 0
            product.save()
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        # Generous limit: DB write dominates; we guard against catastrophic overhead only
        assert avg_ms < 50, f"Average save+signal time {avg_ms:.2f}ms exceeds 50ms"
        assert mock_enqueue.call_count == iterations

    @patch("django_pim.signals.handlers.enqueue_product_sync")
    def test_enqueue_called_for_every_save(self, mock_enqueue):
        """Every model.save() must produce exactly one enqueue call."""
        from tests.factories import ProductFactory

        product = ProductFactory()
        mock_enqueue.reset_mock()

        saves = 20
        for i in range(saves):
            product.is_enabled = i % 2 == 0
            product.save()

        assert mock_enqueue.call_count == saves


# ---------------------------------------------------------------------------
# Suppression prevents all enqueue calls
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.django_db
class SuppressionThroughputTest(TestCase):
    """With suppression active, no enqueue calls should occur regardless of volume."""

    def setUp(self):
        cache.clear()
        _enable_signals()
        is_matrix_signals_enabled()

    def tearDown(self):
        cache.clear()

    @patch("django_pim.signals.handlers.enqueue_product_sync")
    def test_suppression_blocks_all_enqueue_calls(self, mock_enqueue):
        """suppress_matrix_signals must intercept 100% of signals inside the block."""
        from tests.factories import ProductFactory

        with suppress_matrix_signals():
            for _ in range(10):
                ProductFactory()

        mock_enqueue.assert_not_called()

    @patch("django_pim.signals.handlers.enqueue_product_sync")
    def test_suppression_resumes_after_block(self, mock_enqueue):
        """Signals must fire normally once the suppression block is exited."""
        from tests.factories import ProductFactory

        with suppress_matrix_signals():
            ProductFactory()

        mock_enqueue.reset_mock()

        # After block — signals should fire again
        product = ProductFactory()
        mock_enqueue.assert_called_once_with(product.real_product.sku, product.shop.idx)

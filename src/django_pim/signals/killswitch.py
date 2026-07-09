# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import threading
from contextlib import contextmanager

MATRIX_SIGNALS_CACHE_KEY = "pim:matrix_signals_enabled"
GAPS_CACHE_KEY = "pim:gaps_enabled"

_local = threading.local()


def is_matrix_sync_suppressed() -> bool:
    return getattr(_local, "suppress_matrix_sync_depth", 0) > 0


@contextmanager
def suppress_matrix_signals():
    """Suppress signal-driven Matrix sync. Use during bulk imports."""
    _local.suppress_matrix_sync_depth = getattr(_local, "suppress_matrix_sync_depth", 0) + 1
    try:
        yield
    finally:
        _local.suppress_matrix_sync_depth = max(0, _local.suppress_matrix_sync_depth - 1)


def is_matrix_signals_enabled() -> bool:
    """Check PimSettings DB toggle (cached 60s)."""
    from django.core.cache import cache

    cached = cache.get(MATRIX_SIGNALS_CACHE_KEY)
    if cached is not None:
        return cached
    from django_pim.models.pim_settings import PimSettings

    enabled = PimSettings.load().matrix_signals_enabled
    cache.set(MATRIX_SIGNALS_CACHE_KEY, enabled, 60)
    return enabled


def is_gaps_enabled() -> bool:
    """Check the quality-gaps PimSettings toggle (cached 60s).

    Independent of ``matrix_signals_enabled`` — the gap recompute tor runs even when Matrix
    sync is off (the default), so the highlighter still works for those clients.
    """
    from django.core.cache import cache

    cached = cache.get(GAPS_CACHE_KEY)
    if cached is not None:
        return cached
    from django_pim.models.pim_settings import PimSettings

    enabled = PimSettings.load().gaps_enabled
    cache.set(GAPS_CACHE_KEY, enabled, 60)
    return enabled

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Batch gap recompute + rollup repair + the full-recompute lock (etap-03).

Three responsibilities:
- ``recompute_range`` / ``recompute_pks`` — run ``detect_for_product`` over many products with the
  active definitions and the default channel resolved ONCE per batch (etap-02 perf carry-forward),
  not per product. Disjoint PK ranges across parallel batches touch disjoint rows → no deadlocks.
- ``recompute_rollup_for_products`` — recompute the three ``Product`` rollup columns from the
  CURRENT ``GapFinding`` rows, without re-running detection. Used by the rule fast paths
  (severity change, disable, delete) where findings are mutated directly.
- the full-recompute Redis lock — a named lock so a second full recompute coalesces instead of
  starting a second stampede.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Iterable

from django.core.cache import caches
from django.db.models import Count, Max, Min

from .. import settings as pim_settings
from ..models import GapDefinition, GapFinding, Product
from ..models.gap_definition import GapSeverity
from ..models.pim_settings import PimSettings
from . import channel_service
from .gap_detection_service import detect_for_product

logger = logging.getLogger("process")

RECOMPUTE_LOCK_KEY = "pim:gaps:recompute_running"
# Short enough that a SIGKILL mid-pass frees the lock in minutes, not hours — recompute_all refreshes
# it per batch (heartbeat), so a long full pass never lets it expire underneath a live run.
_DEFAULT_LOCK_TTL = 30 * 60


# --- batch recompute ---------------------------------------------------------


def recompute_range(pk_start: int, pk_end: int) -> int:
    """Recompute every product with ``pk_start <= pk < pk_end``. Returns the count processed."""
    return _recompute_qs(Product.objects.filter(pk__gte=pk_start, pk__lt=pk_end))


def recompute_pks(pks: Iterable[int]) -> int:
    """Recompute the given product PKs. Returns the count processed."""
    return _recompute_qs(Product.objects.filter(pk__in=list(pks)))


def recompute_all(progress_cb: Callable[[int, int, int], None] | None = None) -> int:
    """Recompute the whole catalogue in disjoint PK batches of ``PIM_GAPS_BATCH_SIZE``.

    ``progress_cb(batch_start, batch_end, processed)`` is invoked after each batch (for the command's
    progress + timing output). Returns the total count processed. Caller owns the lock + marker;
    each batch refreshes the recompute lock TTL so a long pass never lets it expire mid-run.
    """
    bounds = Product.objects.aggregate(lo=Min("pk"), hi=Max("pk"))
    if bounds["hi"] is None:
        return 0
    batch = pim_settings.PIM_GAPS_BATCH_SIZE
    total = 0
    start = bounds["lo"]
    while start <= bounds["hi"]:
        end = start + batch
        processed = recompute_range(start, end)
        total += processed
        refresh_full_lock()  # heartbeat — keep the lock alive across a long full pass
        if progress_cb is not None:
            progress_cb(start, end, processed)
        start = end
    return total


def _recompute_qs(qs) -> int:
    default_channel = channel_service.get_default_channel()
    all_active = list(GapDefinition.objects.filter(active=True).order_by("display_order", "key"))
    skip_default = PimSettings.load().gaps_skip_default_featureset

    products = qs.select_related("shop", "real_product", "feature_set")
    count = 0
    for product in products.iterator(chunk_size=2000):
        # Scope filter in Python — no per-product query for the definitions.
        scoped = [d for d in all_active if d.channels is None or product.shop.idx in d.channels]
        detect_for_product(product, definitions=scoped, default_channel=default_channel, skip_default=skip_default)
        count += 1
    return count


# --- rollup repair (no re-detection) -----------------------------------------


def recompute_rollup_for_products(pks: Iterable[int]) -> None:
    """Recompute gap_count + gap_worst_severity from CURRENT findings (silent ``.update()``).

    ``gap_evaluated_at`` is left untouched — this is not a re-evaluation, only a rollup repair after
    findings were mutated (severity change / rule disable / rule delete). Bounded: the affected set is
    processed in chunks (a catalogue-wide rule disable can pass a huge PK list), and within each chunk
    counts + the "has a critical" set are aggregated in the DB, never loaded finding-by-finding.
    Updates are grouped by ``(count, worst)`` so a chunk issues a handful of UPDATEs, not one per row.
    Worst severity specialises to the two-level GapSeverity ordering (CRITICAL > WARNING).
    """
    pk_list = list(dict.fromkeys(pks))  # dedupe, preserve order
    if not pk_list:
        return

    chunk_size = pim_settings.PIM_GAPS_BATCH_SIZE
    for i in range(0, len(pk_list), chunk_size):
        _repair_rollup_chunk(pk_list[i : i + chunk_size])


def _repair_rollup_chunk(chunk: list[int]) -> None:
    counts = dict(
        GapFinding.objects.filter(product_id__in=chunk)
        .values_list("product_id")
        .annotate(c=Count("id"))
        .values_list("product_id", "c")
    )
    critical_pids = set(
        GapFinding.objects.filter(product_id__in=chunk, severity=GapSeverity.CRITICAL).values_list(
            "product_id", flat=True
        )
    )

    groups: dict[tuple[int, str | None], list[int]] = defaultdict(list)
    for pk in chunk:
        count = counts.get(pk, 0)
        if count == 0:
            worst = None
        elif pk in critical_pids:
            worst = GapSeverity.CRITICAL
        else:
            worst = GapSeverity.WARNING
        groups[(count, worst)].append(pk)

    for (count, worst), group_pks in groups.items():
        # Silent: .update() does NOT fire post_save → no PIM/Matrix signal loop.
        Product.objects.filter(pk__in=group_pks).update(gap_count=count, gap_worst_severity=worst)


# --- full-recompute lock -----------------------------------------------------


def acquire_full_lock(ttl: int = _DEFAULT_LOCK_TTL) -> bool:
    """Try to take the named full-recompute lock. True = acquired (proceed), False = already running.

    Degrades open when Redis is unavailable (returns True + warning) so a backfill is never blocked
    by a Redis outage — at the cost of the coalesce guarantee in that degraded window.
    """
    try:
        redis_client = caches["default"].client.get_client()
        return bool(redis_client.set(RECOMPUTE_LOCK_KEY, "1", nx=True, ex=ttl))
    except Exception:
        logger.warning("Redis unavailable for gap recompute lock — proceeding without coalesce guard")
        return True


def refresh_full_lock(ttl: int = _DEFAULT_LOCK_TTL) -> None:
    """Extend the lock TTL (heartbeat during a long pass). Caller must already hold the lock."""
    try:
        redis_client = caches["default"].client.get_client()
        redis_client.set(RECOMPUTE_LOCK_KEY, "1", ex=ttl)
    except Exception:
        logger.warning("Redis unavailable refreshing gap recompute lock (may expire mid-run)")


def release_full_lock() -> None:
    try:
        redis_client = caches["default"].client.get_client()
        redis_client.delete(RECOMPUTE_LOCK_KEY)
    except Exception:
        logger.warning("Redis unavailable releasing gap recompute lock (will auto-expire)")


def is_full_recompute_running() -> bool:
    """True when a full recompute currently holds the lock. Degrades to False if Redis is down."""
    try:
        redis_client = caches["default"].client.get_client()
        return bool(redis_client.get(RECOMPUTE_LOCK_KEY))
    except Exception:
        logger.warning("Redis unavailable reading gap recompute lock — reporting not-running")
        return False


def trigger_full_recompute() -> dict:
    """Kick off a full catalogue recompute asynchronously (the 'recompute now' button).

    Idempotent: if a full recompute already holds the lock, returns ``already_running`` without
    dispatching a second pass. The dispatched task re-checks the lock authoritatively (this pre-check
    is only for an immediate, friendly response).
    """
    if is_full_recompute_running():
        return {"status": "already_running"}

    from ..tasks import recompute_gaps_full_task

    if hasattr(recompute_gaps_full_task, "delay"):
        recompute_gaps_full_task.delay()
    else:  # Celery not installed — synchronous fallback
        recompute_gaps_full_task()
    return {"status": "started"}

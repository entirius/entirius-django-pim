# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Celery tasks for the quality-gaps recompute tor (etap-03).

Thin wrappers — all logic lives in the gap services. The tasks register under ``pim.*`` names and are
re-exported in ``tasks/__init__.py`` so Celery's ``autodiscover_tasks`` finds them (otherwise the
worker rejects them as "unregistered"). The host service schedules ``pim.recompute_gaps_nightly`` in
``CELERY_BEAT_SCHEDULE`` and runs a worker on the ``PIM_GAPS_QUEUE`` queue (default ``celery``).
"""

import logging

logger = logging.getLogger("process")


def _flush_gap_recompute() -> dict:
    from django_pim.services import gap_recompute_service
    from django_pim.signals.dispatch import drain_pending_gap_pks

    pks = drain_pending_gap_pks()
    # recompute_pks resolves the active definitions + default channel ONCE for the whole burst
    # (no per-product re-query); products that vanished mid-debounce are simply absent from the qs.
    processed = gap_recompute_service.recompute_pks(pks) if pks else 0
    logger.info("flush_gap_recompute: processed %d/%d pending products", processed, len(pks))
    return {"processed": processed, "pending": len(pks)}


def _detect_for_product(product_pk: int) -> None:
    from django_pim.models import Product
    from django_pim.services.gap_detection_service import detect_for_product

    try:
        product = Product.objects.select_related("shop", "real_product", "feature_set").get(pk=product_pk)
    except Product.DoesNotExist:
        logger.warning("detect_for_product_task: Product pk=%s not found", product_pk)
        return
    detect_for_product(product)


def _recompute_gaps_batch(pk_start: int, pk_end: int) -> dict:
    from django_pim.services import gap_recompute_service

    count = gap_recompute_service.recompute_range(pk_start, pk_end)
    return {"range": [pk_start, pk_end], "processed": count}


def _recompute_gaps_nightly() -> dict:
    """Safeguard: recompute the catalogue only if rules changed since the last full pass."""
    from django_pim.services import gap_recompute_service, gap_rule_service

    if not gap_rule_service.is_catalog_stale():
        return {"skipped": "fresh"}
    if not gap_recompute_service.acquire_full_lock():
        logger.warning("recompute_gaps_nightly: skipped — a full recompute is already running (lock held)")
        return {"skipped": "locked"}
    try:
        count = gap_recompute_service.recompute_all()
        gap_rule_service.mark_recomputed()
        logger.info("recompute_gaps_nightly: recomputed %d products", count)
        return {"recomputed": count}
    finally:
        gap_recompute_service.release_full_lock()


def _recompute_gaps_full() -> dict:
    """Unconditional full recompute (the 'recompute now' button). Coalesces under the full lock."""
    from django_pim.services import gap_recompute_service, gap_rule_service

    if not gap_recompute_service.acquire_full_lock():
        logger.warning("recompute_gaps_full: skipped — a full recompute is already running (lock held)")
        return {"skipped": "locked"}
    try:
        count = gap_recompute_service.recompute_all()
        gap_rule_service.mark_recomputed()
        logger.info("recompute_gaps_full: recomputed %d products", count)
        return {"recomputed": count}
    finally:
        gap_recompute_service.release_full_lock()


try:
    from celery import shared_task

    @shared_task(name="pim.flush_gap_recompute")
    def flush_gap_recompute_task() -> dict:
        return _flush_gap_recompute()

    @shared_task(name="pim.detect_for_product")
    def detect_for_product_task(product_pk: int) -> None:
        _detect_for_product(product_pk)

    @shared_task(name="pim.recompute_gaps_batch")
    def recompute_gaps_batch_task(pk_start: int, pk_end: int) -> dict:
        return _recompute_gaps_batch(pk_start, pk_end)

    @shared_task(name="pim.recompute_gaps_nightly")
    def recompute_gaps_nightly_task() -> dict:
        return _recompute_gaps_nightly()

    @shared_task(name="pim.recompute_gaps_full")
    def recompute_gaps_full_task() -> dict:
        return _recompute_gaps_full()

except ImportError:
    # Celery not installed — synchronous fallbacks so callers/tests still work.
    def flush_gap_recompute_task() -> dict:
        return _flush_gap_recompute()

    def detect_for_product_task(product_pk: int) -> None:
        _detect_for_product(product_pk)

    def recompute_gaps_batch_task(pk_start: int, pk_end: int) -> dict:
        return _recompute_gaps_batch(pk_start, pk_end)

    def recompute_gaps_nightly_task() -> dict:
        return _recompute_gaps_nightly()

    def recompute_gaps_full_task() -> dict:
        return _recompute_gaps_full()

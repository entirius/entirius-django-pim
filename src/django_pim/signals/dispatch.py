# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging
import time

from celery import current_app
from django.core.cache import caches

from django_pim import settings as pim_settings

logger = logging.getLogger("django_pim.signals")


def enqueue_product_sync(sku: str, channel_idx: str) -> None:
    """Add SKU+channel to Redis pending set and schedule a flush task."""
    try:
        redis_client = caches["default"].client.get_client()
    except Exception:
        logger.warning("Redis unavailable, skipping signal sync for SKU=%s channel=%s", sku, channel_idx)
        return

    member = f"{sku}:{channel_idx}"
    score = time.time()
    pending_key = "pim:matrix:pending"
    lock_key = "pim:matrix:flush_scheduled"
    debounce = pim_settings.PIM_MATRIX_SIGNALS_DEBOUNCE_SECONDS

    try:
        redis_client.zadd(pending_key, {member: score})
        redis_client.expire(pending_key, 300)

        if redis_client.set(lock_key, "1", nx=True, ex=debounce + 1):
            current_app.send_task(
                "django_matrix.tasks.flush_pending_matrix_sync", countdown=debounce, queue="matrix_pull"
            )
            logger.info("Flush scheduled in %ds, enqueued SKU=%s channel=%s", debounce, sku, channel_idx)
        else:
            logger.debug("Flush already scheduled, enqueued SKU=%s channel=%s", sku, channel_idx)
    except Exception:
        logger.warning("Redis error during enqueue for SKU=%s channel=%s", sku, channel_idx, exc_info=True)


# --- Quality gaps recompute (etap-03) ---------------------------------------
# Reuses the SHAPE of enqueue_product_sync (debounce zset + SETNX lock + countdown flush) but on
# its OWN Redis keys and OWN flush task. It is deliberately decoupled from the Matrix tor above:
# different gate (PimSettings.gaps_enabled), different keys, different task/queue — so the highlighter
# recomputes even when Matrix sync is off (the default).

GAPS_PENDING_KEY = "pim:gaps:pending"
GAPS_FLUSH_LOCK = "pim:gaps:flush_scheduled"


def enqueue_gap_recompute(product_pk: int) -> None:
    """Debounce a per-product gap recompute and schedule the flush task once."""
    try:
        redis_client = caches["default"].client.get_client()
    except Exception:
        logger.warning("Redis unavailable, skipping gap recompute for product=%s", product_pk)
        return

    member = str(product_pk)
    score = time.time()
    debounce = pim_settings.PIM_GAPS_DEBOUNCE_SECONDS

    try:
        redis_client.zadd(GAPS_PENDING_KEY, {member: score})
        redis_client.expire(GAPS_PENDING_KEY, pim_settings.PIM_GAPS_PENDING_TTL)

        if redis_client.set(GAPS_FLUSH_LOCK, "1", nx=True, ex=debounce + 1):
            current_app.send_task("pim.flush_gap_recompute", countdown=debounce, queue=pim_settings.PIM_GAPS_QUEUE)
            logger.info("Gap flush scheduled in %ds, enqueued product=%s", debounce, product_pk)
        else:
            logger.debug("Gap flush already scheduled, enqueued product=%s", product_pk)
    except Exception:
        logger.warning("Redis error during gap enqueue for product=%s", product_pk, exc_info=True)


def drain_pending_gap_pks() -> list[int]:
    """Pop and return the current pending product PKs (consumer side of the debounce set).

    Lives here next to the producer so one module owns the ``pim:gaps:pending`` key. Idempotent on
    re-run — a second call after a drain returns an empty list.
    """
    try:
        redis_client = caches["default"].client.get_client()
    except Exception:
        logger.warning("Redis unavailable for gap flush — nothing drained")
        return []

    members = redis_client.zrange(GAPS_PENDING_KEY, 0, -1)
    if members:
        redis_client.zrem(GAPS_PENDING_KEY, *members)
    return [int(m.decode() if isinstance(m, bytes) else m) for m in members]

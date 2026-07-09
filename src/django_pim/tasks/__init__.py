"""Celery task package.

``autodiscover_tasks()`` imports ``<app>.tasks`` (this package), so a task module must be imported
here for its ``@shared_task``s to register with the host's Celery app — otherwise the worker rejects
them with "Received unregistered task".
"""

from django_pim.tasks.gaps import (
    detect_for_product_task,
    flush_gap_recompute_task,
    recompute_gaps_batch_task,
    recompute_gaps_full_task,
    recompute_gaps_nightly_task,
)

__all__ = [
    "detect_for_product_task",
    "flush_gap_recompute_task",
    "recompute_gaps_batch_task",
    "recompute_gaps_full_task",
    "recompute_gaps_nightly_task",
]

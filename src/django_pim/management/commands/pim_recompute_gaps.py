# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Recompute quality gaps across the catalogue (etap-03).

The on-demand "Przelicz teraz" backend. Takes the named full-recompute lock so two backfills coalesce
(the second exits immediately). Full runs stamp ``gaps_recomputed_at`` (clears the CMS "rules changed"
alert); partial ``--start/--end`` runs do not.

Usage:
  python manage.py pim_recompute_gaps                      # full catalogue, inline, with timing
  python manage.py pim_recompute_gaps --start 1 --end 50001  # one PK range (no recomputed-at stamp)
  python manage.py pim_recompute_gaps --async             # dispatch one batch task per PK range
"""

import time

from django.core.management.base import BaseCommand
from django.db.models import Max

from django_pim import settings as pim_settings
from django_pim.models import Product
from django_pim.services import gap_recompute_service, gap_rule_service


class Command(BaseCommand):
    help = "Recompute quality gaps for the whole catalogue or a PK range."

    def add_arguments(self, parser):
        parser.add_argument("--start", type=int, default=None, help="First product PK (inclusive)")
        parser.add_argument("--end", type=int, default=None, help="Last product PK (exclusive)")
        parser.add_argument(
            "--async",
            action="store_true",
            dest="run_async",
            help="Dispatch recompute_gaps_batch tasks instead of running inline",
        )

    def handle(self, *args, **options):
        start = options["start"]
        end = options["end"]
        run_async = options["run_async"]
        partial = start is not None or end is not None

        # Async only dispatches fire-and-forget batch tasks — it would release the lock before any task
        # ran, giving false coalesce. So the lock guards the INLINE path only.
        if run_async:
            self._dispatch_async(start, end, partial)
            return

        if not gap_recompute_service.acquire_full_lock():
            self.stdout.write(self.style.WARNING("A full gap recompute is already running — coalescing (no-op)."))
            return
        try:
            self._run_inline(start, end, partial)
        finally:
            gap_recompute_service.release_full_lock()

    # --- inline -------------------------------------------------------------

    def _run_inline(self, start, end, partial: bool) -> None:
        batch = pim_settings.PIM_GAPS_BATCH_SIZE
        t0 = time.monotonic()

        if partial:
            lo = start or 1
            hi = end if end is not None else (Product.objects.aggregate(m=Max("pk"))["m"] or 0) + 1
            total = gap_recompute_service.recompute_range(lo, hi)
            self.stdout.write(f"Range [{lo}, {hi}): {total} products in {time.monotonic() - t0:.1f}s")
            return

        def _progress(batch_start, batch_end, processed):
            self.stdout.write(
                f"  batch [{batch_start}, {batch_end}): {processed} products ({time.monotonic() - t0:.1f}s elapsed)"
            )

        total = gap_recompute_service.recompute_all(progress_cb=_progress)
        gap_rule_service.mark_recomputed()
        elapsed = time.monotonic() - t0
        per_10k = (elapsed / total * 10000) if total else 0
        self.stdout.write(
            self.style.SUCCESS(
                f"Recomputed {total} products in {elapsed:.1f}s "
                f"(~{per_10k:.1f}s/10k, batch_size={batch}). Catalogue marked recomputed."
            )
        )

    # --- async --------------------------------------------------------------

    def _dispatch_async(self, start, end, partial: bool) -> None:
        from django_pim.tasks.gaps import recompute_gaps_batch_task

        batch = pim_settings.PIM_GAPS_BATCH_SIZE
        lo = start or 1
        hi = end if end is not None else (Product.objects.aggregate(m=Max("pk"))["m"] or 0) + 1
        dispatched = 0
        pk = lo
        while pk < hi:
            recompute_gaps_batch_task.delay(pk, min(pk + batch, hi))
            dispatched += 1
            pk += batch
        # Fire-and-forget: no full-recompute lock (it would give false coalesce) and no marker —
        # gaps_recomputed_at is stamped only by an inline full run or the nightly safeguard.
        self.stdout.write(self.style.SUCCESS(f"Dispatched {dispatched} batch task(s) over [{lo}, {hi}) on queue."))
        if not partial:
            self.stdout.write(
                self.style.WARNING("Async full run: gaps_recomputed_at NOT stamped (set it via an inline full run).")
            )

---
title: Cold Start & Backfill
description: First-run options, parallel backfill sizing, the unevaluated window, and migration notes for large catalogs.
---

Quality Gaps grows organically — every product save recomputes that product. But a fresh deployment, or one where you just enabled the feature on an existing catalog, has every product at `gap_evaluated_at=null`. The list shows them all as "unevaluated" until the first full run finishes. This page covers that run.

## Enable the Feature

Gaps are gated by `PimSettings.gaps_enabled`, off by default. Turn it on in Django admin (or a fixture), then confirm the baseline rules are seeded and active. Nothing recomputes until this flag is on.

## The Command

`pim_recompute_gaps` is the backend for the CMS "Recompute now" button. It has three modes:

```bash
# Full catalog, inline, with timing. Takes the full-recompute lock
# (a second run coalesces) and stamps gaps_recomputed_at, which clears
# the CMS "rules changed" alert.
python manage.py pim_recompute_gaps

# One PK range, inline. No lock, no stamp — for parallel backfill.
python manage.py pim_recompute_gaps --start 1 --end 50001

# Dispatch one batch task per PK range onto the queue, fire-and-forget.
# No lock, no stamp.
python manage.py pim_recompute_gaps --async
```

Only an inline full run (`pim_recompute_gaps` with no range) stamps `gaps_recomputed_at`. Range runs and `--async` deliberately don't — so if you backfill in parallel ranges or via `--async`, finish with one inline full run (or let the nightly safeguard) to clear the alert.

## Sizing the Run

The full run processes the catalog in batches of `PIM_GAPS_BATCH_SIZE` (default `10000`).

Calibration on the reference catalog: **~8.6–10.9 ms per product** (10k products in 86–109 s). For a million products that's roughly **2.4–3 hours single-threaded**.

To shorten the window, run disjoint PK ranges in parallel across N workers. Ranges that don't overlap touch different rows, so they don't deadlock:

```bash
# Worker 1
python manage.py pim_recompute_gaps --start 1 --end 250001
# Worker 2
python manage.py pim_recompute_gaps --start 250001 --end 500001
# Worker 3
python manage.py pim_recompute_gaps --start 500001 --end 750001
# Worker 4
python manage.py pim_recompute_gaps --start 750001 --end 1000001
# Then, once all ranges finish, stamp the catalog as recomputed:
python manage.py pim_recompute_gaps
```

## The Unevaluated Window

Until the run completes, products it hasn't reached yet stay at `gap_evaluated_at=null` — the product list shows them as "unevaluated", not "OK". Run the backfill during a low-traffic window, or split it into ranges so the unevaluated set shrinks visibly as workers finish.

## Migration Note

Migration `0052_gap_models` adds the three nullable rollup columns. Adding a nullable column is a metadata-only change in Postgres — instant even on a million rows. But `gap_worst_severity` carries an index, and building that index scans the table and briefly locks writes.

On a large existing `pim_product`, create that index out of band rather than letting the migration block writes:

```sql
CREATE INDEX CONCURRENTLY idx_product_gap_worst_severity
  ON pim_product (gap_worst_severity);
```

`CREATE INDEX CONCURRENTLY` doesn't lock writes, but it can't run inside a transaction — so apply it manually around the migration, then mark the migration faked for that index, or accept the brief write lock on a smaller catalog.

## Nightly Safeguard

A Celery beat task, `pim.recompute_gaps_nightly`, runs at 02:30 UTC. It's a no-op when the catalog is fresh; it triggers a full recompute only when rules changed since the last pass and nobody clicked "Recompute now". It's the net under the manual button — schedule it in the service's `CELERY_BEAT_SCHEDULE`. The reference `fenix-1-volkanos` service already includes it.

## Where to Next

- [Quality Gaps overview](../quality/) — the data model, detection rules, and how recompute is triggered day to day.
- Tune which checks run and at what severity in the CMS rules screen (see the overview's "Configuring Rules in the CMS").

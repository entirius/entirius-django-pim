---
title: Quality Gaps
description: What each product is missing — per channel and language, configurable, at catalog scale.
sidebar:
  label: Overview
  collapsed: true
---

Quality Gaps is a layer inside `django-pim` that flags what a product is missing: no description for a language a channel serves, a too-short text, a missing main image. It works per channel and per language, and the rules live in the database — a client tunes them in the CMS, no deploy.

The highlighter itself is show-only — it tells you what's wrong, it does not fix anything. Two things build on top of it:

- **Spawn rules** (django-enrichment) turn findings into enrichment tasks, manually or on a schedule — see [Spawn Rules](/volkanos/modules/enrichment/spawn-rules/).
- **Exemptions** mute a rule for a product that genuinely is an exception ("this one really doesn't need a long description"). A deep mute: detection stops writing the finding, so the badge, the counters and the enrichment candidates clear at once. `POST {channel}/gaps/exemptions/` with `{sku, definition_key, language?}` (`language` empty = all languages), `DELETE .../{id}/` to unmute — the product is re-detected immediately in both directions.

## Data Model

Two models plus three columns on `Product`. See [Database Diagrams](../erd/) for the full ERD.

| Model | What it holds |
|-------|---------------|
| `GapDefinition` | One configurable check: which check (`check_key`), its params, severity, target languages/channels, an active flag, and a translated label. Lives in the DB so a client tunes it in the CMS without a deploy. |
| `GapFinding` | One failed check on one product, in one language, on one channel. **Sparse** — a product with no problems has zero rows. The table grows with the number of problems, not the size of the catalog. |

The three rollup columns on `pim_product` make the product list sort, filter, and color by quality without joining a second million-row table:

- `gap_worst_severity` — `critical`, `warning`, or `null` (no gaps). Indexed; drives list color and sort.
- `gap_count` — how many findings.
- `gap_evaluated_at` — when this product was last checked. `null` means never evaluated (or unevaluable — see ProductCustom below). `gap_count=0` **with** a timestamp means genuinely clean.

## Detection

Three checks ship in the registry. Each `GapDefinition` picks one and configures it:

| Check | Fails when |
|-------|-----------|
| `feature_present` | The configured feature is empty for the language. |
| `feature_min_length` | The feature's text is shorter than `min_length`. |
| `picture_present` | The product has no picture (optionally for a given role). |

Four correctness rules decide whether a check produces signal or noise:

- **Applicability is FeatureSet membership, not `is_required`.** A check only runs when the feature is in the FeatureSet assigned to the product. If it isn't, the answer is "not applicable" — skipped, not flagged. This is what keeps false gaps out.
- **Languages are channel-served only.** "No `pl` description" is checked against the languages the channel actually serves. A rule targeting "all languages" means all of the channel's languages, not every language in the database.
- **ProductCustom is unevaluated for attribute checks.** Custom products skip attribute-reading checks (their values come from elsewhere); `picture_present` still runs. Their `gap_evaluated_at` stays `null` — the list shows "unevaluated", not "OK".
- **Inherited gaps point to the source.** When a product inherits an empty value from the default channel, the finding is tagged `inherited` with the channel to fix it on. The operator sees "fix on main" instead of chasing the same gap across every channel.

## How Recompute Works

A product's gaps are recomputed by `detect_for_product`, triggered on a separate track from Matrix sync. The cost of a trigger decides how it's handled.

```d2
direction: right

onsave: "Product / attribute /\npicture saved" {
  shape: rectangle
}
sev: "Rule: severity only\nchanged" {
  shape: rectangle
}
cond: "Rule: condition / active\nchanged, or new rule" {
  shape: rectangle
}

debounce: "Debounce + coalesce\n(pim:gaps:* keys)" {
  shape: rectangle
}
detect: "detect_for_product\n(idempotent replace)" {
  shape: rectangle
}
store: "GapFinding rows +\nsilent rollup .update()" {
  shape: rectangle
}

fast: "Fast path:\nbulk-update severity copy\n(no re-detection)" {
  shape: rectangle
}

alert: "CMS alert:\n'rules changed,\nnot recomputed'" {
  shape: rectangle
}
manual: "Operator clicks\n'Recompute now'\nor nightly safeguard" {
  shape: rectangle
}
full: "Full recompute\n(disjoint PK batches)" {
  shape: rectangle
}

onsave -> debounce -> detect -> store
sev -> fast -> store
cond -> alert -> manual -> full
full -> detect
```

| Trigger | Cost | What happens |
|---------|------|--------------|
| Product / attribute / picture saved | Cheap (one product) | Debounced signal recomputes that product. |
| Rule severity changed | Cheap | The denormalized severity copy is bulk-updated. No re-detection. |
| Rule condition / active changed, or a new rule | Expensive (up to 1M) | **Not** automatic. The CMS shows "rules changed — quality not recomputed since [date]" with a "Recompute now" button. A nightly safeguard catches it if nobody clicks. |
| Inheritance propagation | — | Materializing children re-enqueues their recompute, so a fix on the default channel clears the children's findings. |

The whole track is gated by `PimSettings.gaps_enabled`, **off by default** — the operator opts in. It is independent of `matrix_signals_enabled`, so the highlighter recomputes even on a deployment with Matrix sync off.

First-time setup on an existing catalog needs a one-off full run. See [Cold Start & Backfill](../cold-start/).

## Soft Compatibility

The CMS detects the feature by **field presence**, not a capability flag. The product API either includes `gap_worst_severity` / `gap_count` / `gap_evaluated_at` or it doesn't; the CMS optional-chains them with a `null` fallback. An older backend without these fields renders exactly as before — no quality column, no errors.

This is deliberate: quality is a layer inside PIM, not a separate module, so there is no munin "quality" capability to register. The field-presence gate is the whole contract.

## Configuring Rules in the CMS

Rules are seeded from fixtures at onboarding (a baseline template), then the truth lives in the database and the client tunes it in the CMS:

- **Enable or disable** a rule, or add a new one.
- **Change severity** (`critical` / `warning`) — applies immediately, no recompute.
- **Change a condition** (the check, its params, target languages/channels) — needs a recompute; the CMS alert and "Recompute now" button handle it.

Severity is the cheap knob; conditions are the expensive one. The CMS makes the difference visible so an operator isn't surprised by a stale catalog.

## Implementation Notes

Highlighter layer inside PIM (not a separate module) — shows operators what a product is missing, per channel/language, configurably, at ~1M scale.

| Model | Key fields | Notes |
|-------|-----------|-------|
| GapDefinition | `key` (unique), check_key (registry key), params (JSON), languages/channels (JSON, null=all), severity (critical/warning), label_t9n, active, display_order | Config of one check, in DB, tunable in CMS. `BaseModel` (created_at/modified_at). `check_key` not `check` — `check` shadows `Model.check()` |
| GapFinding | `(product, definition, language)` unique, channel_idx (denorm), severity (COPY of definition), inherited, source_channel | **Sparse** — only failing checks get a row (product OK = 0 rows). FK product+definition CASCADE. `BaseModel` |
| GapExemption | `(product, definition, language)` unique **with `nulls_distinct=False`**, reason, created_by | **Deep mute**: detection skips the exempted pair — no finding, no badge, no enrichment candidate. `language=NULL` = all languages + the language-neutral slot. Operator-created rows, so two NULL rows MUST collide (unlike GapFinding). FK CASCADE. `BaseModel` |

Product rollup (3 columns on `pim_product`, drive list sort/filter/colour):
- `gap_worst_severity` (CharField null, db_index) — critical | warning | null
- `gap_count` (int, default 0, **unindexed** — secondary sort)
- `gap_evaluated_at` (DateTime null) — **null = never evaluated / unevaluable (ProductCustom)**; `gap_count=0` + evaluated_at set = genuinely OK

⚠️ Rollup columns are written ONLY via `Product.objects.filter(pk=...).update(...)` — never `instance.save()` (would fire PIM signals → Matrix sync loop). Gap* deliberately use `BaseModel` though the rest of PIM uses plain `models.Model`. Baseline rules seeded from `django_pim_gaps.cfg.yaml` (test-package + host-service fixtures).

**Detection:** `services/gap_check_registry.py` (6 product checks: `feature_present`, `feature_min_length`, `picture_present`, `picture_min_count` (thin gallery — `min_count`+optional `role`, fires only for `1..min_count-1`; `0` stays `picture_present`'s gap, never double-flag; detection-only, no enrichment target_kind), `picture_alt_present` (language-scoped, ALL roles, no pictures = "not applicable" — never double-flag `picture_present`'s gap), `category_present` (structural — product assigned to ≥1 category; language-neutral, never inherited; pairs with the `category` enrichment target_kind); each carries `reads_attributes` / `language_scoped` / a params allowlist) + `services/gap_detection_service.py` → `detect_for_product(product)`. Idempotent transactional replace of a product's findings + silent rollup. Correctness rules: applicability = FeatureSet membership (SYSTEM features always apply, not `is_required`); per-type emptiness read from **raw** fields (NOT `get_value`, which falls back across languages and would mask a missing per-language value); languages = channel-served only; `inherited` is local (empty + non-default channel + `inheritance_enabled` + inherit flag + lang not in `overridden_langs` + not `exclude_from_inheritance` → points to default, no default-channel query). ProductCustom skips attribute checks but still runs `picture_present`; its `gap_evaluated_at` stays NULL ("unevaluated").

**Recompute / triggers:** a SEPARATE track from Matrix sync — own gate (`PimSettings.gaps_enabled`, default off, **independent** of `matrix_signals_enabled`), own Redis keys (`pim:gaps:pending` debounce zset + `pim:gaps:flush_scheduled` lock + `pim:gaps:recompute_running` full lock), own Celery tasks (`pim.flush_gap_recompute`, `pim.detect_for_product`, `pim.recompute_gaps_batch`, `pim.recompute_gaps_nightly`) on `PIM_GAPS_QUEUE` (default `celery`). Highlighter recomputes even with Matrix sync off.

- **On-save** (Product / ProductAttribute / ProductPicture / ProductVideo / ProductInCategory + Feature cascade) → `enqueue_gap_recompute(pk)` (debounced, coalesced). Gap handlers in `signals/handlers.py` (dispatch_uid `*_gaps`) honour `suppress_matrix_signals()` so bulk imports don't stampede — recompute after import via the command. Wide Feature cascade (> `PIM_MATRIX_SIGNALS_BATCH_THRESHOLD`) marks the catalogue stale instead of fanning out.
- **Rule edits** (`GapDefinition` pre/post save + delete): severity-only → `apply_severity_change` fast path (bulk-update the denormalised `severity` copy + silent rollup repair, NO re-detection); condition/active change or new rule → `mark_rules_changed` (drives CMS alert); `active=False` → drop the rule's findings + repair rollups; delete → CASCADE drops findings, rollups repaired from captured PKs.
- **Propagation hook:** inheritance materialisation writes children via `bulk_create`/`bulk_update` which do NOT fire `post_save`, so `propagate_to_inheriting_products` / `propagate_media_to_inheriting` explicitly `enqueue_gap_recompute` for affected children (else a default-channel fix never clears the children's findings).
- **Full recompute:** `services/gap_recompute_service.py` (`recompute_range`/`recompute_all`/`recompute_rollup_for_products` + the `pim:gaps:recompute_running` lock) resolves active definitions + default channel ONCE per batch; disjoint PK ranges → no deadlocks. The `pim_recompute_gaps` command is the on-demand "recompute now" backend (full / `--start/--end` range / `--async`); a full inline run stamps `gaps_recomputed_at`. The nightly safeguard (`pim.recompute_gaps_nightly`, scheduled in the host's `CELERY_BEAT_SCHEDULE`) recomputes only when `is_catalog_stale()` (rules changed since the last pass).

Module state on `PimSettings`: `gaps_enabled`, `gaps_rules_changed_at`, `gaps_recomputed_at` (migration `0053_pimsettings_gaps`). 4 concurrency guards: full-recompute lock + debounce coalesce + idempotent per-product replace + disjoint PK batches.

**Admin API:** `api/admin/views/gaps_views.py` (JWT + IsAdminUser, thin over services):
- `GapDefinitionViewSet` — rule CRUD (`gap_definition_service`). Create/update/delete use plain `.save()`/`.delete()` so the GapDefinition signals own the lifecycle reactions — the service must NOT call `gap_rule_service` (double-fire). `check_key`/`params` validated via `gap_check_registry.validate_params`; updates gated by an editable-field whitelist (`key` immutable).
- `GapFindingViewSet` — `GET {channel}/gaps/findings/?product_ids=` bulk labels for a page, grouped by product PK, sparse (`gap_query_service`). `language` keeps language-neutral findings; `severity`/`only_source` filters.
- `GapExemptionViewSet` — `GET/POST {channel}/gaps/exemptions/` (list requires `?sku=`) + `DELETE .../{pk}/`. Create/delete call `detect_for_product` **directly** (sync — the mute takes effect immediately, independent of `gaps_enabled`); delete verifies the channel (no cross-channel pk guessing).
- `GapOpsViewSet` — `gaps/recompute/` dispatches `recompute_gaps_full_task` (202 + lock status, idempotent → `already_running`); `gaps/status/` returns the rules-changed-vs-recomputed signal (`get_gaps_status`); `gaps/settings/` GET/PATCH exposes `gaps_skip_default_featureset` — a real change stamps `gaps_rules_changed_at`, so the CMS "recompute now" alert lights up.
- **Soft-compat:** `gap_worst_severity`/`gap_count`/`gap_evaluated_at` are added to the product list + detail responses, and the product list sort allowlist (`ORDERING_MAP`) + a `gap_severity` filter. Old backend without these fields → CMS optional-chains them (no munin capability — `quality` is a layer, not a module). Product-list ordering keeps its silent-fallback contract; strict sort→400 is enforced on the new GapDefinition list. Bad `gap_severity` value → 400.

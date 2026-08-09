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

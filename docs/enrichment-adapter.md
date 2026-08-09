---
title: Enrichment Adapter
description: How PIM implements the enrichment adapter contract.
---

`src/django_pim/services/enrichment_adapter.py` is PIM's read/write boundary for the
[django-enrichment](../../django-enrichment/AGENTS.md) bus — the **referential** adapter (decision
D1: the adapter lives in the source module, not in the bus).

The bus never imports PIM. It loads this adapter lazily by dotted **module** path from the host
service's settings:

```python
ENRICHMENT_ADAPTERS = {"pim": "django_pim.services.enrichment_adapter"}
```

and calls five module-level functions (duck-typed against `django_enrichment.adapters.base`).
This file imports nothing from `django-enrichment` — the dependency points one way: bus → contract.

## Contract

| Function | Direction | Purpose |
|----------|-----------|---------|
| `resolve_targets(scope_spec, page=1)` | READ | A scope → a page of SKUs (lazy, channel-scoped) |
| `find_gaps(check, params, scope)` | READ | Quality-gap candidates from materialised `GapFinding` rows (etap-13) — see below |
| `read_current(*, subject_ref, target_kind, target_locator)` | READ | Authoritative current value → drift / diff / undo snapshot |
| `apply(proposal)` | WRITE | Write `proposed_value` into PIM (the only enrichment→PIM write site) |
| `revert(proposal)` | WRITE | Restore `current_snapshot` (single-level undo) |

## Locator / value convention

The bus treats these as opaque — only this adapter reads them.

- `subject_ref` = product SKU
- `target_kind` = `"attribute_value"` (text) | `"picture"` (media, etap-08) | `"feature_set"`
  (classification, featureset-cascade etap-02) | `"picture_alt"` (alt texts, etap-05-extra)

| target_kind | `target_locator` | `proposed_value` | `current_snapshot` |
|-------------|------------------|------------------|--------------------|
| `attribute_value` | `{"channel", "language", "feature_idx"}` | `{"text": <value for that language>}` | `{"text": <raw stored value, "" if absent>}` |
| `picture` | `{"channel"}` | `{"op": "replace_main", "alt_t9n": {...}}` | `{"sha1", "role", "position", "alt_t9n", "url"}` of the old main, `{}` if none |
| `feature_set` | `{"channel"}` | `{"featureset_idx": <idx of an existing FeatureSet>}` | `{"featureset_idx": <current idx, "" if product missing>}` |
| `picture_alt` | `{"channel", "language"}` | `{"alts": {"<picture_pk>": <alt for that language>}}` | `{"alts": {"<picture_pk>": <stored alt, "" if absent>}}` of ALL pictures, `{"alts": {}}` if product missing |

Scope specs (`resolve_targets` / `find_gaps`):

```jsonc
{"mode": "list",   "module": "pim", "channel": "<idx>", "refs": ["SKU-1", "SKU-2"]}
{"mode": "filter", "module": "pim", "channel": "<idx>", "filters": {"is_enabled": true, "category_idx": "..."}}
{"mode": "gap",    "module": "pim", "check": "<GapDefinition.key>", "scope": {"channel": "<idx>", "language": "<iso2>"?}}
```

Only a whitelist of `list_products` kwargs is honoured in `filters`
(`search`, `is_enabled`, `visibility`, `product_class`, `category_idx`, `has_media`) — anything else
is ignored, so a worker can't inject arbitrary query kwargs.

## Two gotchas the adapter owns (the bus stays dumb)

**1. Read-merge-write.** PIM's write path (`product_service.update_product` →
`_set_product_attributes`) deletes and recreates the whole attribute row per feature. Writing a
single language would wipe the others, so `apply`/`revert` read the current `value_txt_t9n`, merge
the one proposed language in, and write the full dict back.

**2. Inheritance override.** A write on a **secondary** (non-default) channel whose product inherits
the relevant feature would be clobbered by the next materialisation. So after writing, the language
is marked in `ProductAttribute.overridden_langs` — but **only** when inheritance is actually enabled
for that flag (`inherit_descriptions` for `DESCRIPTION_FEATURE_IDXS`, else `inherit_attributes`) on a
non-default channel. Default-channel writes set no override (the default channel is the inheritance
source). The attribute exists post-write, so the adapter sets `overridden_langs` directly rather than
going through `toggle_language_override` (which raises unless inheritance is enabled and the
attribute already exists).

`read_current` reads the **raw** `value_txt_t9n[language]`, never `ProductAttribute.get_value`
(which falls back across languages) — a fallback would make drift comparisons and undo restore the
wrong string.

## Classification writes (`target_kind=feature_set`, featureset-cascade etap-02)

The first **classification gap**: the AI resolves it by picking an existing PIM entity (a
`FeatureSet` idx, grounded by `GET feature-sets/` which returns idx/name/desc/is_default), not by
writing free text. Language-neutral — the locator carries no language, and the matching
`feature_set_default` findings are written with `language=NULL`.

`apply`/`revert` resolve `featureset_idx` (unknown or empty → `ValueError`, fail loud) and write via
`product.save(update_fields=["feature_set"])` — deliberately **not** a silent `.update()` (decision
PO 2026-06-10). The `post_save` signals must fire: the gap handler enqueues a recompute that clears
the structural finding and surfaces the now-applicable attribute gaps (the cascade), and Matrix
re-syncs set membership. No signal loop — the silent-`.update()` rule covers only the rollup columns
written *inside* detection.

## Alt-text writes (`target_kind=picture_alt`, featureset-cascade etap-05-extra)

One proposal covers **all pictures of the product for one language** — the same granularity as the
`picture_alt_present` finding (one sparse row per `(product, language)`, all roles). Picture pks
travel as **string** keys: `proposed_value`/`current_snapshot` are JSON columns on the proposal and
JSON object keys are always strings; the adapter parses them back to ints (non-numeric →
`ValueError`).

Apply is a per-picture **read-merge-write** on `alt_text_t9n`: the proposed language is merged into
each picture's existing dict — sibling languages and pictures absent from the map are never touched.
All-or-nothing: every pk is validated against the product **before** any write and the batch runs in
one `transaction.atomic()`, so an unknown/foreign pk raises `ValueError` with zero partial writes.
Writes go through `pp.save(update_fields=["alt_text_t9n"])` so `post_save` fires the gap recompute
(the finding clears) and the Matrix sync (the read model picks the new alt up).

Empty-state semantics differ from `feature_set`: an apply with an empty `alts` map — or any
empty/whitespace alt string — is worker misuse (`ValueError`; an applied `""` would never clear
the finding and the enrichment loop would respawn the candidate forever). A **revert**, by
contrast, may restore `""` (a snapshotted empty state) and treats an empty snapshot
(`{"alts": {}}` — no pictures at intake) as a no-op.

## find_gaps (etap-13)

`check` = a `GapDefinition.key`; unknown → `ValueError` (the bus surfaces it as a 400).
`scope.channel` is required; `scope.language` optionally narrows (language-neutral `NULL` findings
are kept alongside, mirroring `gap_query_service`). `params` is accepted per the cross-module
contract but **ignored** — PIM's rule parameters live on the `GapDefinition` row itself.

Reads the **materialised** `GapFinding` table (never recomputes live):

- `inherited=False` only — an inherited gap is fixed on the source channel; writing on an
  inheriting channel would create unwanted `overridden_langs` overrides.
- Deep-muted targets are absent for free: a `GapExemption` stops detection from ever writing the
  finding (see AGENTS.md § Quality Gaps).
- Stable paging by `(product_id, language)`, page size 100 (`scope["page"]`, injected by the bus).

One finding → one plain-dict candidate (gaps-per-module shape):

```jsonc
{
  "target_module": "pim", "target_type": "product", "subject_ref": "<sku>",
  "priority": "critical|warning", "definition_key": "<rule key>",
  // feature checks:
  "target_kind": "attribute_value",
  "target_locator": {"channel": "<idx>", "language": "<iso2|null>", "feature_idx": "<idx>"}
  // picture_present:     target_kind="picture",     target_locator={"channel": "<idx>"}
  // picture_alt_present: target_kind="picture_alt", target_locator={"channel": "<idx>", "language": "<iso2>"}
  // feature_set_default: target_kind="feature_set", target_locator={"channel": "<idx>"}
}
```

The bus post-filters these against in-flight proposals and re-pulls page 1 as a work queue —
that contract lives bus-side (`django-enrichment` `docs/spawn-surfaces.md` § Gap spawn).

## Scope limits (etap-04)

- Text only: `apply`/`revert` raise `ValueError` for non-`*_T9N` features (a t9n payload sent to a
  scalar feature would otherwise be silently dropped by `_set_product_attributes`).
- Media apply (`target_kind=picture`) is etap-08; mass async apply is etap-09.

## Tests

`tests/test_enrichment_adapter.py` — read-merge-write (sibling languages preserved), override on an
inheriting secondary channel vs none on the default channel, `revert`, `resolve_targets`
filter/list, non-t9n rejection. Run inside Docker:

```bash
PIM_TEST_DB_HOST=db python -m pytest tests/test_enrichment_adapter.py -q
```

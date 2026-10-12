---
title: Lookup Provider
description: How PIM feeds the lookup module and runs the advisory duplicate check on product create.
---

## Lookup provider

`services/lookup_provider.py` is PIM's read boundary for the **django-lookup** module (dedup /
"do we have something like this?"). Same shape as the enrichment adapter: lookup loads it lazily from
`LOOKUP_PROVIDERS = {"pim_product": "django_pim.services.lookup_provider"}` and calls duck-typed
module-level functions (`iter_items`, `get_item`, `basic`/`basics`, `detail_url`/`detail_urls`,
`signal_specs`; the plural display pair is the optional batch extension lookup prefers — without it
one hit costs two full prefetch round trips). It imports nothing from django-lookup —
`ProviderItem` / `BasicData` are mirrored here so an optional consumer never becomes a PIM
dependency.

One item per `RealProduct`, `ref` = SKU. Identifiers and physicals come from the RealProduct;
display data (name t9n, `brand` / `mpn` features, MAIN picture path) from ONE product — the first
enabled one, else the first by id — since a RealProduct projects into many channels. `signal_specs()`
declares the senders lookup connects so a fingerprint follows the catalog: `RealProduct` saves,
`Product` saves **and deletes**, `ProductAttribute` saves **and deletes** for `name` / `brand` /
`mpn`, MAIN `ProductPicture` saves and deletes. The `Product` sender is what makes the CMS edit path
visible: `_set_product_attributes` writes with `bulk_create` (no per-row signal) and `update_product`
compensates with a single `post_save` for the Product — none of the specs may declare `watch`, or
that compensating send (which never passes `pre_save`) gets filtered out and renames stop refreshing
the fingerprint.

The `post_delete` legs are free here: a `post_delete` receiver normally costs a model its
fast-delete, which would be a bad trade on `ProductAttribute` (bulk-deleted on every product
update), but `signals/handlers.py` already connects matrix-sync receivers to both senders. Every
`ref()` resolver returns `None` rather than raising when the parent row is already gone — it runs
inside a signal handler, so a `DoesNotExist` would abort the delete that triggered it.

Two writers reach the tables without signals and compensate by hand:
`bulk_update_products` (`queryset.update()`) calls `lookup_provider.enqueue_refresh` for an
`is_enabled` toggle — that flag decides which Product `_display_product` picks, so the whole
fingerprint follows it; `visibility` needs nothing, the fingerprint never reads it. And because
`iter_items(since=...)` filters `RealProduct.updated_at` while display data lives on other tables,
the service write paths (`update_product`, `delete_product`, `bulk_update_products`, the three
`product_picture_service` mutations) call `touch_real_product` so `lookup_backfill --since` catches
renames and picture swaps, not just identifier edits. A write that bypasses those services — a raw
`queryset.update()`, a data migration, a fixture load — still needs a full backfill.

## Lookup create hook

`services/lookup_bridge.py` is PIM's *call* side of the same boundary — the mirror image of
`lookup_provider.py`. `POST {channel}/products/` runs an advisory duplicate check before creating:
`build_query` turns the create request into a `LookupQuery` payload (ean, `name`/`brand`/`mpn`
attributes in the channel language, physicals, `limit` 5, no `scope` so lookup searches every
registered kind; `name` / `brand` / `mpn` are truncated to `LookupQuery`'s `max_length`, since an
over-long name would otherwise make `LookupQuery(**payload)` raise and switch the advisory check
off for exactly the long-titled products most likely to be duplicates), and `possible_duplicates` calls `lookup_service.check`, which scores the
candidates and logs a `DedupDecision` per candidate. The answer rides back in the create response as
`possible_duplicates[]` (+ `lookup_warnings[]`); both are empty on GET.

Never blocks, never links: the create is not conditional on the answer and nothing is written to
`RealProduct`. Every failure degrades to a warning — module absent → `lookup_unavailable`, anything
else → `lookup_failed` — so an optional module can never cost the caller its product. The hook sits
in the view, not in `create_product`: the service is also the import path, which must stay free of a
per-row lookup call. Its response shape is mirrored in `schemas/responses/lookup.py` (a Pydantic
annotation is resolved at class definition time, so importing lookup's schema would make the
optional module a hard dependency and the OpenAPI document deployment-dependent).
The hook runs when the host registers a `pim_product` provider in `settings.LOOKUP_PROVIDERS` — one source of truth, no separate flag; an unconfigured host gets a silent no-op.

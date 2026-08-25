# AGENTS.md

Product Information Management module for the Volkanos ecommerce platform — distribution
`entirius-django-pim`, Django app `django_pim`. Full CRUD Admin API (v2) for products, categories,
features, feature sets, attributes, attributes groups, product links, pictures, files, and videos.

**Tech:** Python >=3.11, Django >=5.0, DRF, Pydantic, drf-spectacular

## Commands

| Command | Meaning |
|---|---|
| `make install` | sync dependencies (uv, incl. extras) |
| `make check` | lint + format-check (ruff) |
| `make fix` | auto-fix lint + format |
| `make test` | test suite (pytest + pytest-django) |

## Conventions

- English only: code, docs, commits, branches, PRs.
- MPL-2.0: every non-trivial source file carries the license header (pre-commit inserts it).
- Toolchain: uv + ruff + hatchling + pytest; all config in `pyproject.toml`; `uv.lock` committed.
- Git flow: `master` (production) + `develop` (integration); changes land via PR; semver tag on `master`.
- Never rename the package / Django app_label / DB table prefix `django_pim` — it is a schema contract.
- Migrations are part of the public contract — never edit an already released migration.
- Default: do not commit — git is the user's call.
## Signals

PIM publishes Django signals on model changes (Product, ProductAttribute, Feature, Attribute, etc.)
that trigger automatic Matrix read model sync via Celery tasks. Disabled by default — enable via
`PimSettings.matrix_signals_enabled` in Django admin.

Key files:
- `signals/handlers.py` — all signal handlers
- `signals/dispatch.py` — Redis debounce + Celery task scheduling
- `signals/killswitch.py` — context manager + PimSettings check

See [Signal-Driven Sync](https://docs.entirius.com/volkanos/patterns/signal-driven-sync/) for full architecture.

## Enrichment Adapter

`services/enrichment_adapter.py` is PIM's read/write boundary for the **django-enrichment** bus —
the *referential* adapter (decision D1: the adapter lives in the source module, not the bus). The
bus loads it lazily by dotted module path from the host service's `ENRICHMENT_ADAPTERS = {"pim":
"django_pim.services.enrichment_adapter"}` and calls five duck-typed module-level functions
(`resolve_targets`, `find_gaps`, `read_current`, `apply`, `revert`). It imports nothing from
django-enrichment — the dependency points one way (bus → contract).

Two gotchas it owns so the bus stays dumb: **read-merge-write** (PIM's write path replaces the whole
`value_txt_t9n` per feature, so a single-language write merges into the full dict — never lose
sibling languages) and **inheritance override** (a write on an inheriting secondary channel marks
the language in `overridden_langs` so materialisation won't clobber it; no-op on the default channel
or non-inheriting products). Five target_kinds: `attribute_value` (text, `*_T9N` features),
`picture` (replace_main, etap-08), `feature_set` (classification — AI picks an existing set idx;
apply uses `product.save(update_fields=["feature_set"])` so the gap-recompute cascade and Matrix
sync fire, featureset-cascade etap-02), `category` (classification — AI picks existing categories,
`{"category_idxs": [...]}`, full-replace via `product_service.update_product`; apply requires a
non-empty list, revert restores the snapshot incl. empty = "no categories"; pairs with the
`category_present` gap), `picture_alt` (alt texts, etap-05-extra — one proposal =
ALL pictures × ONE language, `{"alts": {"<picture_pk>": alt}}` with STRING pk keys (JSON), per-picture
read-merge-write on `alt_text_t9n`, all-or-nothing via `transaction.atomic`, writes through
`pp.save(update_fields=["alt_text_t9n"])`). `find_gaps` (etap-13)
reads materialised `GapFinding` rows (`check` = `GapDefinition.key`, `inherited` excluded,
deep-muted targets absent by construction) and returns plain-dict candidates — full contract:
`docs/enrichment-adapter.md`.

## Lookup Provider

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
`Product` saves, `ProductAttribute` saves for `name` / `brand` / `mpn`, MAIN `ProductPicture` saves
and deletes. The `Product` sender is what makes the CMS edit path visible: `_set_product_attributes`
writes with `bulk_create` (no per-row signal) and `update_product` compensates with a single
`post_save` for the Product — none of the specs may declare `watch`, or that compensating send
(which never passes `pre_save`) gets filtered out and renames stop refreshing the fingerprint.

## Lookup Create Hook

`services/lookup_bridge.py` is PIM's *call* side of the same boundary — the mirror image of
`lookup_provider.py`. `POST {channel}/products/` runs an advisory duplicate check before creating:
`build_query` turns the create request into a `LookupQuery` payload (ean, `name`/`brand`/`mpn`
attributes in the channel language, physicals, `limit` 5, no `scope` so lookup searches every
registered kind), and `possible_duplicates` calls `lookup_service.check`, which scores the
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

## Architecture

```
src/django_pim/
├── models/                         # 38 ORM models
│   ├── product.py                  #   Product (base), ProductQuerySet, ProductManager
│   │                               #   Product: +inherit_attributes, +inherit_descriptions, +inherit_images (3 bool flags)
│   ├── real_product.py             #   RealProduct (SKU/EAN, shared across channels)
│   ├── product_simple/             #   ProductSimple (O2O → Product)
│   ├── product_configurable/       #   ProductConfigurable (O2O → Product)
│   ├── product_bundle/             #   ProductBundle, BundleLink, BundleSection
│   ├── product_custom/             #   ProductCustom, ProductAttributeCustomImage
│   ├── product_attribute.py        #   ProductAttribute (feature values per product)
│   │                               #   ProductAttribute: +overridden_langs (JSONField, override tracking)
│   ├── feature.py                  #   Feature (14 types, 3 scopes, 13 system features, +exclude_from_inheritance)
│   ├── feature_set.py              #   FeatureSet, FeatureInFeatureSet (M2M with position)
│   ├── attribute.py                #   Attribute, AttributeModifier
│   ├── attributes_group.py         #   AttributesGroup (clusters of attributes)
│   ├── product_category.py         #   ProductCategory (hierarchical, per channel)
│   ├── product_in_category.py      #   ProductInCategory (assignment with position)
│   ├── channel.py                  #   Channel (formerly Shop, migration 0047)
│   │                               #   Channel: +is_default, +inheritance_enabled, +default_inheritance_flags
│   ├── picture.py, thumb.py        #   Picture/Thumb (SHA1 dedup, auto-delete)
│   ├── product_picture.py          #   ProductPicture (role: MAIN/GENERAL/VARIANT/ANGLE, +is_inherited)
│   ├── video.py, product_video.py  #   Video (youtube/vimeo auto-detect), ProductVideo +is_inherited
│   ├── files.py, product_file.py   #   Files (PDF/DOC/VIDEO/PICTURE), ProductFile +is_inherited
│   ├── files_category.py           #   FilesCategory (manual/datasheet/certificate/warranty)
│   ├── product_price.py            #   ProductPrice (per product + currency)
│   ├── product_link_type.py        #   ProductLinkType (configurable, migration 0049-0050)
│   ├── product_links.py            #   ProductLink (FK → ProductLinkType)
│   └── pim_settings.py             #   PimSettings (singleton, global PIM behavior config)
│
├── managers/                       # 13 manager modules (legacy import/sync utilities)
│   ├── product.py                  #   ProductManager (generate_sku, soft delete)
│   ├── feature.py                  #   FeatureManager (cached lookup, idx generation)
│   ├── category.py                 #   CategoryManager (tree traversal, Redis cached)
│   ├── attribute.py                #   AttributeManager (cached, special char slugify)
│   ├── channel.py                  #   ChannelManager (cached lookup)
│   └── product_attribute.py        #   ProductAttributeManager (MULTISELECT handling)
│
├── api/admin/                      # v2 Admin API (JWT + IsAdminUser)
│   ├── views/                      #   14 ViewSets + 2 upload APIViews
│   ├── urls.py                     #   Route definitions
│   ├── pagination.py               #   AdminPageNumberPagination (20/page, max 100)
│   └── permissions.py              #   IsAdminUser (is_staff or is_superuser)
│
├── views/api_viewer/               # Legacy v1 read-only views
│
├── schemas/
│   ├── requests/                   # 13 files, ~25 Pydantic models (create/update/bulk)
│   └── responses/                  # 12 files, ~28 Pydantic models (list/detail + nested)
│
├── services/                       # Business logic (~70 functions across 12 modules)
│   ├── product_service.py          #   list, get, detail, create, update, delete, bulk_update
│   ├── category_service.py         #   list, get, detail, create, update, delete
│   ├── feature_service.py          #   list, get, create, update, delete, resolve_name
│   ├── feature_set_service.py      #   list, get, create, update, delete, bulk_add/remove
│   ├── attribute_service.py        #   list, get, create, update, delete, resolve_name
│   ├── attributes_group_service.py #   list, get, create, update, delete, resolve_name
│   ├── product_link_type_service.py #  list, get, create, update, delete, resolve_name
│   ├── product_link_service.py     #   list, get, create, update, delete
│   ├── product_picture_service.py  #   upload, list, get, link, update, unlink
│   ├── files_category_service.py   #   list, get, create, update, delete, resolve_name
│   ├── product_file_service.py     #   upload, list, link, unlink
│   ├── product_video_service.py    #   list, get, create, update, delete
│   └── inheritance_service.py      #   materialize, copy, add-to-channel, toggle, propagate
│
├── tasks/                          # Celery tasks
│   └── inheritance.py              #   propagate_translations_task (async propagation)
│
├── filters/                        # 5 filter classes (v1 catalog filtering)
│   ├── product_filter.py           #   SKU, category, search, price range, attribute query
│   ├── category_filter.py          #   parent, tree_deep
│   ├── feature_filter.py           #   category, is_filterable/searchable/comparable
│   └── feature_set_filter.py       #   category
│
├── settings.py                     # T9N_DEFAULT_LANG="pl", 13 system feature idxs
├── admin.py                        # Django admin
└── urls.py                         # v1 + v2 URL routing
```

Layer rule: `API → Services → Models → DB`. No ORM in views.

---

## Admin API v2

All endpoints: JWT + IsAdminUser. Prefix: `/api/pim/v2/admin/`

```
pim/admin/
├── {channel_idx}/                          # Channel-scoped resources
│   ├── products/                           GET (list), POST (create)
│   │   ├── bulk/                           POST (bulk update)
│   │   ├── {sku}/                          GET (detail), PATCH, DELETE
│   │   ├── {sku}/links/                    GET (list), POST (create)
│   │   │   └── {pk}/                       GET, PATCH, DELETE
│   │   ├── {sku}/pictures/                 GET (list), POST (link or upload+link)
│   │   │   └── {pk}/                       GET, PATCH, DELETE (unlink)
│   │   ├── {sku}/files/                    GET (list), POST (link or upload+link)
│   │   │   └── {pk}/                       DELETE (unlink)
│   │   ├── {sku}/videos/                   GET (list), POST (create)
│   │   │   └── {pk}/                       GET, PATCH, DELETE
│   │   ├── {sku}/copy-attributes/           POST (copy from source channel)
│   │   ├── {sku}/copy-translations/        POST (alias for copy-attributes)
│   │   ├── {sku}/add-to-channel/           POST (create on target channel)
│   │   ├── {sku}/toggle-override/          POST (toggle language inheritance)
│   │   └── {sku}/toggle-media-override/    POST (toggle media inherited/local)
│   ├── gaps/findings/                      GET (bulk findings for ?product_ids=, +language/severity/only_source)
│   ├── gaps/exemptions/                    GET (?sku=), POST (mute a rule for a product)
│   │   └── {pk}/                           DELETE (unmute)
│   ├── categories/                         GET (list), POST (create)
│   │   └── {idx}/                          GET (detail), PATCH, DELETE
│   ├── features/                           GET (channel-scoped list)
│   │   └── {idx}/                          GET (channel-scoped detail)
│   │       └── attributes/                 GET (attributes for feature)
│   ├── feature-sets/                       GET (channel-scoped list)
│   │   └── {idx}/                          GET (channel-scoped detail)
│   │       └── features/                   GET (features in set)
│   └── attributes-groups/                  GET (channel-scoped list)
│       └── {idx}/                          GET (channel-scoped detail)
│
├── gap-definitions/                        GET (list), POST (create)   # quality rules (global)
│   └── {key}/                              GET, PATCH, DELETE
├── gaps/recompute/                         POST (trigger full recompute → 202 + lock status)
├── gaps/status/                            GET (rules-changed vs recomputed + recompute_running)
├── gaps/settings/                          GET, PATCH (gaps_skip_default_featureset — CMS toggle)
├── link-types/                             GET (list), POST (create)
│   └── {idx}/                              GET, PATCH, DELETE
├── pictures/upload/                        POST (multipart, 10MB max)
├── files-categories/                       GET (list), POST (create)
│   └── {code}/                             GET, PATCH, DELETE
├── files/upload/                           POST (multipart, 50MB max)
├── features/                               GET (list), POST (create)
│   ├── {idx}/                              GET, PATCH, DELETE
│   │   └── attributes/                     GET (attributes for feature)
│   └── {feature_idx}/attributes/           POST (create attribute)
├── feature-sets/                           GET (list), POST (create)
│   └── {idx}/                              GET, PATCH, DELETE
│       └── features/                       GET, POST (bulk add), DELETE (bulk remove)
├── attributes/                             GET (list)
│   └── {feature_idx}/{idx}/               GET, PATCH, DELETE  (composite key)
└── attributes-groups/                      GET (list), POST (create)
    └── {idx}/                              GET, PATCH, DELETE
```

**Scope rules:**
- **Channel-scoped** (Products, Categories, sub-resources): all CRUD under `{channel_idx}/`
- **Global + channel read** (Features, Feature Sets, Attributes Groups): writes global, reads both
- **Global only** (Attributes, Link Types, Files Categories): composite key or idx/code
- **Upload endpoints** (Pictures, Files): global, SHA1 dedup, multipart

Full schema/parameter details: `docs/api-reference.md`

---

## Product Model

```
RealProduct (sku↑, ean, weight, width, height, deep)     ← shared across channels
    └── Product (visibility, is_enabled, product_class)    ← per channel + feature_set
         ├── ProductAttribute (feature + value_*)           ← per feature in feature_set
         ├── ProductInCategory (category + position)
         ├── ProductPicture (picture + role + language)
         ├── ProductVideo, ProductFile, ProductPrice
         └── ProductLink (related/crosssell/upsell)
              └── Subtypes: Simple | Configurable | Bundle | Custom  (O2O inheritance)
```

Inheritance (3 independent flags per product):
- Product.inherit_attributes (bool) — inherits all features EXCEPT name/description/short_description
- Product.inherit_descriptions (bool) — inherits name, description, short_description
- Product.inherit_images (bool) — inherits ProductPicture, ProductVideo, ProductFile
- ProductAttribute.overridden_langs (JSONField) — per-attribute language override tracking
- ProductPicture/ProductVideo/ProductFile.is_inherited (bool) — marks inherited media
- Channel.is_default (bool) — source of truth for inheritance
- Channel.inheritance_enabled (bool) — master switch per channel
- Channel.default_inheritance_flags (JSONField) — defaults for new products (["attributes", "descriptions", "images"])
- DESCRIPTION_FEATURE_IDXS = {"name", "description", "short_description"} — categorizes features
- Propagation: default channel update → inheriting products re-materialized (attributes + media)

- `create_product` → `get_or_create` RealProduct by SKU (reuses across channels)
- `update_product` → shared fields (weight, EAN) affect ALL channels
- `delete_product` → removes channel Product only, not RealProduct
- PATCH `attributes` → replaces per `feature_idx`, untouched features stay
- PATCH `category_idxs` → full replace of all assignments

---

## Quality Gaps (pim-quality-score)

Highlighter layer inside PIM (not a separate module) — shows operators what a product is missing, per channel/language, configurably, at ~1M scale. API/CMS land in later etaps; etap-01 is the data model, etap-02 is detection.

| Model | Key fields | Notes |
|-------|-----------|-------|
| GapDefinition | `key` (unique), check_key (registry key), params (JSON), languages/channels (JSON, null=all), severity (critical/warning), label_t9n, active, display_order | Config of one check, in DB, tunable in CMS. `BaseModel` (created_at/modified_at). `check_key` not `check` — `check` shadows `Model.check()` |
| GapFinding | `(product, definition, language)` unique, channel_idx (denorm), severity (COPY of definition), inherited, source_channel | **Sparse** — only failing checks get a row (product OK = 0 rows). FK product+definition CASCADE. `BaseModel` |
| GapExemption | `(product, definition, language)` unique **with `nulls_distinct=False`**, reason, created_by | **Deep mute** (etap-13): detection skips the exempted pair — no finding, no badge, no enrichment candidate. `language=NULL` = all languages + the language-neutral slot. Operator-created rows, so two NULL rows MUST collide (unlike GapFinding). FK CASCADE. `BaseModel` |

Product rollup (3 columns on `pim_product`, drive list sort/filter/colour):
- `gap_worst_severity` (CharField null, db_index) — critical | warning | null
- `gap_count` (int, default 0, **unindexed** — secondary sort)
- `gap_evaluated_at` (DateTime null) — **null = never evaluated / unevaluable (ProductCustom)**; `gap_count=0` + evaluated_at set = genuinely OK

⚠️ Rollup columns are written ONLY via `Product.objects.filter(pk=...).update(...)` — never `instance.save()` (would fire PIM signals → Matrix sync loop). Gap* deliberately use `BaseModel` though the rest of PIM uses plain `models.Model`. Baseline rules seeded from `django_pim_gaps.cfg.yaml` (test-package + host-service fixtures).

**Detection (etap-02):** `services/gap_check_registry.py` (6 product checks: `feature_present`, `feature_min_length`, `picture_present`, `picture_min_count` (thin gallery — `min_count`+optional `role`, fires only for `1..min_count-1`; `0` stays `picture_present`'s gap, never double-flag; detection-only, no enrichment target_kind), `picture_alt_present` (etap-05-extra: language-scoped, ALL roles, no pictures = "not applicable" — never double-flag `picture_present`'s gap), `category_present` (structural — product assigned to ≥1 category; language-neutral, never inherited; pairs with the `category` enrichment target_kind); each carries `reads_attributes` / `language_scoped` / a params allowlist) + `services/gap_detection_service.py` → `detect_for_product(product)`. Idempotent transactional replace of a product's findings + silent rollup. Correctness rules: applicability = FeatureSet membership (SYSTEM features always apply, not `is_required`); per-type emptiness read from **raw** fields (NOT `get_value`, which falls back across languages and would mask a missing per-language value); languages = channel-served only; `inherited` is local (empty + non-default channel + `inheritance_enabled` + inherit flag + lang not in `overridden_langs` + not `exclude_from_inheritance` → points to default, no default-channel query). ProductCustom skips attribute checks but still runs `picture_present`; its `gap_evaluated_at` stays NULL ("nieoceniony").

**Recompute / triggers (etap-03):** a SEPARATE tor from Matrix sync — own gate (`PimSettings.gaps_enabled`, default off, **independent** of `matrix_signals_enabled`), own Redis keys (`pim:gaps:pending` debounce zset + `pim:gaps:flush_scheduled` lock + `pim:gaps:recompute_running` full lock), own Celery tasks (`pim.flush_gap_recompute`, `pim.detect_for_product`, `pim.recompute_gaps_batch`, `pim.recompute_gaps_nightly`) on `PIM_GAPS_QUEUE` (default `celery`). Highlighter recomputes even with Matrix sync off.

- **On-save** (Product / ProductAttribute / ProductPicture / ProductVideo / ProductInCategory + Feature cascade) → `enqueue_gap_recompute(pk)` (debounced, coalesced). Gap handlers in `signals/handlers.py` (dispatch_uid `*_gaps`) honour `suppress_matrix_signals()` so bulk imports don't stampede — recompute after import via the command. Wide Feature cascade (> `PIM_MATRIX_SIGNALS_BATCH_THRESHOLD`) marks the catalogue stale instead of fanning out.
- **Rule edits** (`GapDefinition` pre/post save + delete): severity-only → `apply_severity_change` fast path (bulk-update the denormalised `severity` copy + silent rollup repair, NO re-detection); condition/active change or new rule → `mark_rules_changed` (drives CMS alert); `active=False` → drop the rule's findings + repair rollups; delete → CASCADE drops findings, rollups repaired from captured PKs.
- **Propagation hook:** inheritance materialisation writes children via `bulk_create`/`bulk_update` which do NOT fire `post_save`, so `propagate_to_inheriting_products` / `propagate_media_to_inheriting` explicitly `enqueue_gap_recompute` for affected children (else a default-channel fix never clears the children's findings).
- **Full recompute:** `services/gap_recompute_service.py` (`recompute_range`/`recompute_all`/`recompute_rollup_for_products` + the `pim:gaps:recompute_running` lock) resolves active definitions + default channel ONCE per batch; disjoint PK ranges → no deadlocks. The `pim_recompute_gaps` command is the on-demand "Przelicz teraz" backend (full / `--start/--end` range / `--async`); a full inline run stamps `gaps_recomputed_at`. The nightly safeguard (`pim.recompute_gaps_nightly`, scheduled in the host's `CELERY_BEAT_SCHEDULE`) recomputes only when `is_catalog_stale()` (rules changed since the last pass).

Module state on `PimSettings`: `gaps_enabled`, `gaps_rules_changed_at`, `gaps_recomputed_at` (migration `0053_pimsettings_gaps`). 4 concurrency guards: full-recompute lock + debounce coalesce + idempotent per-product replace (etap-02) + disjoint PK batches.

**Admin API (etap-04):** `api/admin/views/gaps_views.py` (JWT + IsAdminUser, thin over services):
- `GapDefinitionViewSet` — rule CRUD (`gap_definition_service`). Create/update/delete use plain `.save()`/`.delete()` so the GapDefinition signals own the lifecycle reactions — the service must NOT call `gap_rule_service` (double-fire). `check_key`/`params` validated via `gap_check_registry.validate_params`; updates gated by an editable-field whitelist (`key` immutable).
- `GapFindingViewSet` — `GET {channel}/gaps/findings/?product_ids=` bulk labels for a page, grouped by product PK, sparse (`gap_query_service`). `language` keeps language-neutral findings; `severity`/`only_source` filters.
- `GapExemptionViewSet` (etap-13) — `GET/POST {channel}/gaps/exemptions/` (list requires `?sku=`) + `DELETE .../{pk}/`. Create/delete call `detect_for_product` **directly** (sync — the mute takes effect immediately, independent of `gaps_enabled`); delete verifies the channel (no cross-channel pk guessing).
- `GapOpsViewSet` — `gaps/recompute/` dispatches `recompute_gaps_full_task` (202 + lock status, idempotent → `already_running`); `gaps/status/` returns the rules-changed-vs-recomputed signal (`get_gaps_status`); `gaps/settings/` GET/PATCH exposes `gaps_skip_default_featureset` (featureset-cascade etap-04) — a real change stamps `gaps_rules_changed_at`, so the CMS "recompute now" alert lights up.
- **Soft-compat:** `gap_worst_severity`/`gap_count`/`gap_evaluated_at` are added to the product list + detail responses, and the product list sort allowlist (`ORDERING_MAP`) + a `gap_severity` filter. Old backend without these fields → CMS optional-chains them (no munin capability — `quality` is a layer, not a module). Product-list ordering keeps its silent-fallback contract; strict sort→400 is enforced on the new GapDefinition list. Bad `gap_severity` value → 400.

---

## Key Enums

| Enum | Values |
|------|--------|
| **FeatureType** | BOOL(1), DECIMAL(2), VARCHAR255(3), VARCHAR255_T9N(4), TEXT(5), TEXT_T9N(6), SELECT(7), MULTISELECT(8), JSON(9), DATETIME(10), JSON_T9N(11), TEMPERATURE(12), LENGTH(13), MASS(14) |
| **FeatureScope** | SYSTEM(1), ~~GLOBAL(2)~~ (deprecated→BU), BUSINESS_UNIT(3) |
| **ProductClass** | Simple(1), Configurable(2), Bundle(3), Custom(4) |
| **Visibility** | NOT_VISIBLE(1), CATALOG(2), SEARCH(3), CATALOG_AND_SEARCH(4) |
| **PictureRole** | MAIN(1), GENERAL(2), VARIANT(3), ANGLE(4) |
| **VideoRole** | UNKNOWN(0), MAIN(1), VARIANT(2) |
| **FileRole** | UNDEFINED(0), PICTURE(1), PDF(2), DOC(3), VIDEO(4) |
| **VideoSource** | youtube, vimeo, unknown (TextChoices, auto-detected from URL) |

---

## Unique Constraints

| Model | Field(s) | Type |
|-------|----------|------|
| Feature | `idx` | unique |
| FeatureSet | `idx` | unique |
| AttributesGroup | `idx` | unique (migration 0048) |
| ProductCategory | `(shop, idx)` | UniqueConstraint |
| RealProduct | `Lower(sku)` | UniqueConstraint |
| Attribute | `(feature, idx)` | UniqueConstraint (composite key) |
| ProductAttribute | `(product, feature, attribute)` | UniqueConstraint |
| ProductInCategory | `(product, category)` | unique |
| ProductLinkType | `idx` | unique |
| FilesCategory | `code` | unique |
| ProductLink | `(product, linked_product, link_type)` | unique_together |
| ProductFile | `(product, file)` | unique_together |
| ProductPicture (MAIN) | `(product, picture_role, language)` | UniqueConstraint (conditional) |
| ProductVideo (MAIN) | `(product, video_role, language)` | UniqueConstraint (conditional) |
| GapDefinition | `key` | unique |
| GapFinding | `(product, definition, language)` | unique_together |
| GapExemption | `(product, definition, language)` | UniqueConstraint (`nulls_distinct=False`) |

---

## Testing

~230 tests. Requires Postgres. The quality-gap suite spans 9 files (models → detection → recompute →
signals → API → golden correctness → concurrency → perf). Opt-in `@pytest.mark.slow` tests are
deselected by default (`addopts = -m "not slow"`); run them with `-m slow`.

```bash
pytest                                                    # local (slow tests skipped)
DATABASE_URL=postgresql://… python -m pytest tests/ -x -q    # custom postgres
PIM_PERF_N=10000 python -m pytest tests/test_perf_gaps.py -m slow -s -q   # perf calibration
```

| File | Tests | Scope |
|------|-------|-------|
| `test_admin_api.py` | ~40 | Read-only (list, retrieve, auth, pagination) |
| `test_admin_api_crud.py` | ~88 | Full CRUD: products, categories, features, feature sets, attributes, attributes groups |
| `test_admin_api_links.py` | ~23 | LinkType CRUD + ProductLink CRUD + auth + constraints |
| `test_admin_api_pictures.py` | ~17 | Upload + SHA1 dedup + gallery CRUD + role constraints |
| `test_admin_api_files.py` | ~17 | FilesCategory CRUD + upload + ProductFile link/unlink |
| `test_admin_api_videos.py` | ~14 | ProductVideo CRUD + source auto-detect + role constraints |
| `test_admin_api_inheritance.py` | ~56 | Inheritance: channel default, materialization, propagation, copy, add-to-channel, toggle, API endpoints |
| `test_models.py` | 13 | Quality gaps: GapDefinition/GapFinding constraints + defaults, Product rollup columns, FK CASCADE, silent `.update()`, seed idempotency |
| `test_services.py` | ~31 | Gap detection (etap-02) + rollup repair / propagation hook (etap-03) |
| `test_signals_gaps_dispatch.py` | 8 | Gap debounce: own `pim:gaps:*` keys, own flush task/queue, coalesce, Redis degradation |
| `test_signals_gaps.py` | 12 | Gap on-save enqueue (independent of Matrix flag) + GapDefinition lifecycle (fast path / stale / cleanup) |
| `test_tasks_gaps.py` | 9 | Flush→detect, batch==per-product, full-lock coalesce, nightly stale/fresh/locked |
| `test_api_gaps.py` | ~46 | Gap admin API: GapDefinition CRUD + auth, bulk findings, exemptions CRUD (etap-13), recompute/status, product soft-compat (gap_* + sort/filter), 500-no-leak |
| `test_gap_exemptions.py` | ~14 | Deep mute (etap-13): detection skip per pair/language/neutral slot, create→finding gone + silent rollup, delete→restored, service validation |
| `test_correctness_golden.py` | 10 | Golden correctness (etap-07), fixtures-driven: FeatureSet applicability, custom "nieoceniony", MULTISELECT/DECIMAL emptiness, inherited→source_channel + cleanup-after-propagation E2E, fixture-drift guard |
| `test_concurrency.py` | 6 | Concurrency manifest (etap-07): idempotency, full-lock coalesce, severity fast-path, cleanup, silent rollup (no loop), disjoint-batch isolation |
| `test_perf_gaps.py` | slow | 10k `recompute_range` calibration (opt-in `@pytest.mark.slow`); baseline ~8–11 ms/product |
| `test_api.py` | varies | Legacy v1 |

Factories in `tests/factories.py`: Channel, Feature, FeatureSet, Attribute, AttributesGroup, RealProduct, Product, ProductCategory, ProductAttribute, FeatureInFeatureSet, ProductLinkType, ProductLink, FilesCategory, GapDefinition, GapFinding.

Golden-gaps fixture: `tests/fixtures/gaps_golden.yaml` (deterministic catalogue — channels, features, rules, products), mirrored in `entirius-test-package/fixtures/django_pim_gaps_golden.cfg.yaml` for seed/init reuse. Regenerable via `tests/_golden_data.py::emit_fixture` (builds in a rolled-back transaction, serialises to YAML).

---


## Gotchas

- Tests need Postgres 15+ — set `DATABASE_URL` (default `postgresql://postgres:postgres@localhost:5432/test`)
- RealProduct fields (weight, EAN, dimensions) are shared -- updating affects all channels
- `AttributesGroup.idx` was missing unique constraint before migration 0048
- `T9N_DEFAULT_LANG` defaults to `"pl"` not `"en"` -- affects name resolution fallback
- 13 system features (pk 1-13) are auto-created by CSV importer -- do NOT duplicate in FeatureInFeatureSet fixtures
- SYSTEM features are protected via API -- cannot change scope, feature_type, or is_required; cannot delete. Service layer raises ValueError, views return 400
- GLOBAL scope (2) is deprecated -- data migration 0056 converts existing GLOBAL features to BUSINESS_UNIT. API blocks scope=1 (schema) and scope=2 (service layer)
- Managers in `managers/` are legacy import utilities (cached, stateful) -- v2 admin API uses `services/` only
- Feature type TEXT (5) columns don't use language suffix; TEXT_T9N (6) DO use suffix
- `ProductLinkType` was migrated from IntEnumChoices to a Django model (migrations 0049-0050). Old int values map to PKs: 1=related, 2=crosssell, 3=upsell, 4=navigation
- Picture upload: SHA1 is computed in both the service (for dedup check) and the model's `save()` (for storage). They use the same algorithm
- Videos are URL-based only (no file upload). Video.save() auto-detects source from URL (YouTube/Vimeo)
- `PimSettings` is a singleton (pk=1 always) — use `PimSettings.load()` to get-or-create
- Default channel cannot be deleted (ProtectedError raised)
- `overridden_langs=[]` means all languages inherit; `["en"]` means English is user-controlled
- Inheritance only works for features in the FeatureSet intersection between channels
- Propagation is synchronous by default; use Celery task for async at scale
- Inheritance requires `Channel.inheritance_enabled=True` — False disables all inheritance for that channel
- `DESCRIPTION_FEATURE_IDXS = {"name", "description", "short_description"}` separates description from attribute inheritance
- Media inheritance copies pictures/videos/files with `is_inherited=True`; local media (`is_inherited=False`) preserved during re-materialization
- **Quality Gaps rollup columns (`gap_*`) are written ONLY via `Product.objects.filter(pk=...).update(...)`** — `instance.save()` fires PIM signals → Matrix sync loop. `product_post_save` does not fire on `QuerySet.update`
- **The gap recompute track is independent of Matrix sync** — own gate (`PimSettings.gaps_enabled`, default off, NOT `matrix_signals_enabled`), own Redis keys (`pim:gaps:*`), own tasks/queue. The highlighter recomputes even with Matrix sync off
- **Gap applicability = FeatureSet membership, not `is_required`** — a check runs only when the feature is in the product's FeatureSet; otherwise "not applicable" (skipped), not "empty". Gap emptiness reads RAW fields, never `get_value` (which falls back across languages and masks per-language gaps)
- **ProductCustom `gap_evaluated_at` stays NULL** ("unevaluated") — custom products skip attribute checks but still run `picture_present`. NULL evaluated_at = never/unevaluable; `gap_count=0` + a timestamp = genuinely clean
- **Deep mute = zero finding rows** (etap-13) — a `GapExemption` makes detection skip the pair, so badges, rollups and `find_gaps` candidates all clear at once. `gap_exemption_service` re-detects the product **directly** on create/delete (sync, independent of `gaps_enabled`); the rollup still goes through the silent `.update()` inside detection
- **`find_gaps` reads materialised findings and excludes `inherited`** — the fix belongs on the source channel; writing through enrichment on an inheriting channel would create unwanted `overridden_langs` overrides. `params` is accepted but ignored (rule params live on `GapDefinition`)
- **`picture_alt` proposals carry STRING picture-pk keys** (etap-05-extra) — `proposed_value`/`current_snapshot` are JSON, so `{"alts": {"42": "alt"}}`, never int keys. Apply validates every pk against the product BEFORE writing (unknown/foreign pk → `ValueError`, zero partial writes); revert with `{"alts": {}}` is a legit no-op (no pictures at intake), unlike `feature_set` where an empty snapshot is a hard error

---

## Reference Docs

| File | Content |
|------|---------|
| `docs/api-reference.md` | Full API surface: all request/response schemas, parameters, error codes |
| `docs/models-reference.md` | Complete model inventory: fields, relationships, managers, enums |
| `docs/erd-config.yaml` | ERD diagram config for `make erd` |
| `docs/enrichment-adapter.md` | Enrichment bus adapter contract, locator convention, read-merge-write + override gotchas |
| entirius-docs `volkanos/modules/pim/quality/` | User-facing Quality Gaps docs: feature overview, detection rules, soft compatibility, cold-start/backfill ops |

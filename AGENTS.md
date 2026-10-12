# AGENTS.md

`entirius-django-pim` (Django app `django_pim`) — Product Information Management module of Entirius: full CRUD
Admin API (v2) for products, categories, features, feature sets, attributes, attributes groups, product links,
pictures, files and videos, plus channel inheritance and quality gaps.

## Commands

| Command | Meaning |
|---|---|
| `make install` | sync dependencies (uv, incl. extras) |
| `make check` | lint + format-check (ruff) |
| `make fix` | auto-fix lint + format |
| `make test` | test suite (pytest + pytest-django) |

Tests need PostgreSQL 15 or newer: set `DATABASE_URL` (the default in `tests/settings.py` points at a local postgres).

## Conventions

- English only: code, docs, commits, branches, PRs.
- MPL-2.0: every non-trivial source file carries the license header (pre-commit inserts it).
- Toolchain: uv + ruff + hatchling + pytest; all config in `pyproject.toml`; `uv.lock` committed.
- Git flow: `master` (production) + `develop` (integration); changes land via PR; semver tag on `master`.
- Never rename the package / Django app_label / DB table prefix `django_pim` — it is a schema contract.
- Migrations are part of the public contract — never edit an already released migration.
- Default: do not commit — git is the user's call.
- Access: areas live on the AppConfig (`access_areas`, `access_route_rules`), every admin view carries
  `access_area`; a new admin route without one fails `tests/test_access_ownership.py`.
- No AI attribution in commits or PR descriptions.

## Architecture

```
src/django_pim/
├── models/                         # ORM models
│   ├── product.py                  #   Product (base), ProductQuerySet, ProductManager
│   │                               #   Product: +inherit_attributes, +inherit_descriptions, +inherit_images (3 bool flags)
│   ├── real_product.py             #   RealProduct (SKU/EAN, shared across channels)
│   ├── product_simple/             #   ProductSimple (O2O → Product)
│   ├── product_configurable/       #   ProductConfigurable (O2O → Product)
│   ├── product_bundle/             #   ProductBundle, BundleLink, BundleSection
│   ├── product_custom/             #   ProductCustom, ProductAttributeCustomImage
│   ├── product_attribute.py        #   ProductAttribute (feature values per product)
│   │                               #   ProductAttribute: +overridden_langs (JSONField, override tracking)
│   ├── feature.py                  #   Feature (types, scopes, system features, +exclude_from_inheritance)
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
├── managers/                       # legacy import/sync utilities
│   ├── product.py                  #   ProductManager (generate_sku, soft delete)
│   ├── feature.py                  #   FeatureManager (cached lookup, idx generation)
│   ├── category.py                 #   CategoryManager (tree traversal, Redis cached)
│   ├── attribute.py                #   AttributeManager (cached, special char slugify)
│   ├── channel.py                  #   ChannelManager (cached lookup)
│   └── product_attribute.py        #   ProductAttributeManager (MULTISELECT handling)
│
├── api/admin/                      # v2 Admin API (JWT + IsAdminUser)
│   ├── views/                      #   ViewSets + upload APIViews
│   ├── urls.py                     #   Route definitions
│   ├── pagination.py               #   AdminPageNumberPagination (20/page, max 100)
│   └── permissions.py              #   IsAdminUser (is_staff or is_superuser)
│
├── views/api_viewer/               # Legacy v1 views, staff JWT only
│
├── schemas/
│   ├── requests/                   # Pydantic models (create/update/bulk)
│   └── responses/                  # Pydantic models (list/detail + nested)
│
├── services/                       # Business logic
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
│   ├── inheritance_service.py      #   materialize, copy, add-to-channel, toggle, propagate
│   ├── enrichment_adapter.py       #   read/write boundary for the enrichment bus
│   ├── lookup_provider.py          #   read boundary for the lookup module
│   ├── lookup_bridge.py            #   advisory duplicate check on product create
│   └── gap_*_service.py            #   quality gaps: registry, detection, recompute, rules, queries
│
├── signals/                        # handlers.py, dispatch.py (Redis debounce), killswitch.py
├── tasks/                          # Celery tasks
│   └── inheritance.py              #   propagate_translations_task (async propagation)
│
├── filters/                        # filter classes (v1 catalog filtering)
│   ├── product_filter.py           #   SKU, category, search, price range, attribute query
│   ├── category_filter.py          #   parent, tree_deep
│   ├── feature_filter.py           #   category, is_filterable/searchable/comparable
│   └── feature_set_filter.py       #   category
│
├── settings.py                     # T9N_DEFAULT_LANG, system feature idxs, units, signal and gap tuning
├── admin.py                        # Django admin
└── urls.py                         # v1 + v2 URL routing
```

Layer rule: `API → Services → Models → DB`. No ORM in views.

Signals: PIM publishes Django signals on model changes (Product, ProductAttribute, Feature, Attribute, …) that
trigger the Matrix read-model sync through Celery; off by default, enabled by `PimSettings.matrix_signals_enabled`
in Django admin. Pattern: https://docs.entirius.com/architecture/signal-driven-sync/

Boundaries to optional modules are duck-typed and import nothing from them: the enrichment bus loads
`services/enrichment_adapter.py`, the lookup module loads `services/lookup_provider.py`, and product create calls
lookup through `services/lookup_bridge.py` (advisory, never blocks). Quality gaps are a layer inside PIM with their
own gate (`PimSettings.gaps_enabled`), Redis keys and Celery tasks.

| Topic | Where |
|---|---|
| Full API surface: routes, schemas, parameters, error codes | `docs/api-reference.md` |
| Model inventory, product model, enums, unique constraints | `docs/models-reference.md` |
| ERD config for the docs ERD generator | `docs/erd-config.yaml`, `docs/erd.md` |
| Enrichment adapter contract, locator convention | `docs/enrichment-adapter.md` |
| Lookup provider, create hook | `docs/lookup-provider.md` |
| Quality gaps: model, detection, recompute, admin API | `docs/quality.md`, `docs/cold-start.md` |
| Channel inheritance | `docs/inheritance.md` |
| Required features, feature scope | `docs/required-features.md`, `docs/feature-scope.md` |
| Management commands | `docs/commands.md` |
| Testing, factories, golden fixture | `docs/testing.md` |
| More gotchas | `docs/gotchas.md` |

## Gotchas

- Tests need Postgres 15+ — set `DATABASE_URL` (default `postgresql://postgres:postgres@localhost:5432/test`)
- RealProduct fields (weight, EAN, dimensions) are shared -- updating affects all channels
- `T9N_DEFAULT_LANG` defaults to `"en"` -- affects name resolution fallback
- 13 system features (pk 1-13) are auto-created by CSV importer -- do NOT duplicate in FeatureInFeatureSet fixtures
- SYSTEM features are protected via API -- cannot change scope, feature_type, or is_required; cannot delete. Service layer raises ValueError, views return 400
- GLOBAL scope (2) is deprecated -- data migration 0056 converts existing GLOBAL features to BUSINESS_UNIT. API blocks scope=1 (schema) and scope=2 (service layer)
- Managers in `managers/` are legacy import utilities (cached, stateful) -- v2 admin API uses `services/` only
- Feature type TEXT (5) columns don't use language suffix; TEXT_T9N (6) DO use suffix
- `PimSettings` is a singleton (pk=1 always) — use `PimSettings.load()` to get-or-create
- Default channel cannot be deleted (ProtectedError raised)
- `overridden_langs=[]` means all languages inherit; `["en"]` means English is user-controlled
- Inheritance only works for features in the FeatureSet intersection between channels
- Inheritance requires `Channel.inheritance_enabled=True` — False disables all inheritance for that channel
- `DESCRIPTION_FEATURE_IDXS = {"name", "description", "short_description"}` separates description from attribute inheritance
- **Quality Gaps rollup columns (`gap_*`) are written ONLY via `Product.objects.filter(pk=...).update(...)`** — `instance.save()` fires PIM signals → Matrix sync loop. `product_post_save` does not fire on `QuerySet.update`
- **The gap recompute track is independent of Matrix sync** — own gate (`PimSettings.gaps_enabled`, default off, NOT `matrix_signals_enabled`), own Redis keys (`pim:gaps:*`), own tasks/queue. The highlighter recomputes even with Matrix sync off
- **Gap applicability = FeatureSet membership, not `is_required`** — a check runs only when the feature is in the product's FeatureSet; otherwise "not applicable" (skipped), not "empty". Gap emptiness reads RAW fields, never `get_value` (which falls back across languages and masks per-language gaps)
- **ProductCustom `gap_evaluated_at` stays NULL** ("unevaluated") — custom products skip attribute checks but still run `picture_present`. NULL evaluated_at = never/unevaluable; `gap_count=0` + a timestamp = genuinely clean
- **Deep mute = zero finding rows** — a `GapExemption` makes detection skip the pair, so badges, rollups and `find_gaps` candidates all clear at once. `gap_exemption_service` re-detects the product **directly** on create/delete (sync, independent of `gaps_enabled`); the rollup still goes through the silent `.update()` inside detection
- **`find_gaps` reads materialised findings and excludes `inherited`** — the fix belongs on the source channel; writing through enrichment on an inheriting channel would create unwanted `overridden_langs` overrides. `params` is accepted but ignored (rule params live on `GapDefinition`)

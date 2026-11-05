# Changelog

## Unreleased

### Added

- Enrichment: `attribute_value` proposals apply to LENGTH features as `{"value": "6.5", "unit": "inch"}`. The value is
  converted on write and stored in `DEFAULT_LENGTH_UNIT`, rounded to `UNIT_CONVERSION_DECIMAL_PLACES`.
- Enrichment: `attribute_value` proposals now apply to DECIMAL and BOOL (`{"value": ...}`) and to VARCHAR255 and TEXT
  (`{"text": ...}`). `read_current` returns the same shapes; an empty value is restore-only, so only revert removes the
  row. A decimal reads back in plain digits, so a stored 12.500000 and a proposed 12.5 are not drift.
- Gaps: `feature_present` and `feature_min_length` accept an optional `required_only` param (bool). With it the
  check applies only where the product's feature set requires the feature — the membership's `is_required`
  override, else the feature's own flag — so one definition per feature gates exactly the sets that require it,
  instead of every set that merely contains it. Default unchanged (membership). No migration.

## 3.7.0 — 2026-11-11

### Fixed

- Gap recompute and signal dispatch work with Django's built-in `django.core.cache.backends.redis.RedisCache`, not
  only django-redis. They reached the raw client through django-redis's `.client`, so on the built-in backend every
  lock and pending-set call raised and took the degraded path ("Redis unavailable ...") while Redis was up.
  `django_pim.services.redis_client` returns the writer client for either backend.

### Added

- Admin API: `GET {channel}/categories/` items carry `subcategory_count` (direct children), `position` and
  `parent_category_idx`, so a CMS can render a lazy tree over `root_only` and `parent_category=<pk>`. Additive: no
  field removed or renamed.

### Changed

- Admin API: `search` on `GET {channel}/categories/` matches case-insensitively the name values of the channel's
  languages (default language and `languages`) or the `idx`. It used to match the JSON text of `name_t9n`, so a
  language key (`en`, `pl`), `"` or `:` matched every category and `idx` was not searched. Fewer false hits, idx hits
  added.

### Performance

- Admin API: `product_count` and `subcategory_count` on the category list are correlated subqueries, so only the rows
  of the page are counted and the paginator's `count()` carries no aggregate (a GROUP BY over every category of the
  channel ran on each page). The channel's default language is joined, which removes a query per row from `name` and
  `url_key` (a page of 20 took 24 queries, now 4, whatever the page size).


## 3.6.1 — 2026-11-04

### Security

- Admin API: no exception text reaches a response (CodeQL `py/stack-trace-exposure`, 42 alerts). A refusal the PIM
  writes for the client is an `InvalidRequestError` (`django_pim.exceptions`, a `ClientError` and still a
  `ValueError` for direct callers); the views answer only its `client_message`. Any other `ValueError` from a lower
  layer answers 500 `INTERNAL_ERROR` with a `debug_id`, its text goes to the log. The gap exemption routes answer an
  `ObjectDoesNotExist` with `NotFound("Not found")` (the v2 handler already replaced the 404 text).
- CI: the workflow token is read-only (`permissions: contents: read`, CodeQL `actions/missing-workflow-permissions`).

### Changed

- Admin API: a `ValueError` the PIM did not raise as a refusal answers 500 instead of 400 with its text, on every
  admin route that answered a service `ValueError` with a 400. The refusals the services, `ProductAttribute.save()`,
  `FeatureInFeatureSet` and the validators write on those routes (duplicate idx/SKU, SYSTEM feature, circular
  category, inheritance off, unknown role/language/ordering/severity/gap params, a bad idx, SKU or EAN from
  `idx_normalizator`) keep their 400 (409 for add-to-channel) and their message.
- Admin API: a non-integer `visibility` or `product_class` on `{channel}/products/`, `page` or `page_size` on
  `{channel}/categories/{idx}/products/` and `position` on a picture upload answer 400 naming the parameter instead
  of 400 with Python's `invalid literal for int()`; `page` below 1 and a negative `page_size` there answer the same
  400 instead of Django's "Negative indexing is not supported.". An empty `scope`, `feature_type` or
  `parent_category` is ignored like the other empty filters instead of a 400.

### Fixed

- Admin API: `files/upload/` with an unknown `file_type` answers 400 `Invalid file type: ...` instead of 500, and a
  picture upload with a bad `position` is refused before the picture is stored (it left an unlinked picture).

## 3.6.0 — 2026-11-04

### Changed

- **Admin API error bodies: clients that read `detail` read the v2 envelope instead** (`message`, and
  `details[].description` for a 400). Every error answers `{error, message, debug_id, details[]}` instead of
  `{"detail": ...}`; status codes are unchanged. The views raise DRF exceptions (`NotFound`, `ValidationError`, a
  409 `Conflict`) and the service's v2 handler builds the body; a 500 keeps its `error_id`, now as `debug_id`. A
  404 carries the generic `message` (the old text goes to the log), a 400 from a service rule keeps its text in
  `details[0].description`. On the legacy alias `/api/pim/admin/` the service's non-v2 handler formats the raised
  errors (Volkanos: contentdb `{meta, data}`), so its bodies change too; no in-tree client parses them.
- Requires `entirius-django-utils>=2.4.0` (query location on validation details, a 409 keeps its message).

### Fixed

- Admin API: `gaps/findings/` without `product_ids`, with non-integers or with more than 200 ids names
  `product_ids` (`location: "query"`); so do `gaps/exemptions/` without `sku`, `features/` with a bad `scope` or
  `feature_type` and `categories/` with a bad `parent_category`. The findings operation documents the 400 and the
  `product_ids` limit in OpenAPI.
- Admin API: an unknown channel on `{channel}/feature-sets/` (list, detail, features) and
  `{channel}/attributes-groups/`, and an unknown channel or product on the picture, video, link and file routes
  under `products/{sku}/.../{pk}/`, answer 404 `NOT_FOUND` instead of 500.
- Admin API: `PATCH products/{sku}/links/{pk}/` with an unknown `link_type_idx` answers 404 and with a link type that
  another link between the same products already has answers 400, like create; both were 500. A duplicate link lost
  to a concurrent create or update answers the same 400 instead of 500.
- OpenAPI: the 200 of every admin list operation (channels, products, categories and their products, features,
  feature sets, attributes, attributes groups, link types, files categories, gap definitions, gap findings, gap
  exemptions, and a product's files, links, pictures and videos; 20 under `/api/pim/v2/admin/`, 17 of them in the
  published service spec, and their `/api/pim/admin/` twins) describes the object the view returns instead of an
  array of it: a page `{count, next, previous, results}`, `{results}` (gap findings keyed by product pk, gap
  exemptions), or `{positioned, unpositioned, ...}` (category products). The bodies are unchanged.

## 3.5.0 — 2026-10-27
- Admin API: a page out of range (`?page=0`, past the last page) answers 404 `NOT_FOUND` in the v2 envelope
  instead of 500, in every admin list view; a `page_size` that is not a positive integer answers 400
  `VALIDATION_ERROR` instead of falling back and staying in the `next` link (#24).
- Access: attribute values are their own area, `pim.attribute_values` (entirius-django-access 1.1.0): the
  `attributes/` admin routes need it instead of `pim.schema`, so an integration can add a value (a new brand option)
  without the right to change features, feature sets or channels. Built-in roles keep their rights; access migration
  `0007` gives every custom role holding `pim.schema` the same level on the new area. Run it with
  `entirius-django-access>=1.1.0`: with 1.0.x the Editor role only reads `attributes/` and custom roles get no right
  on it (no migration `0007`); PIM does not depend on access, so the service lock pairs them.
- Enrichment adapter: derived pictures (the AI image worker) — `apply_modes(target_kind, target_locator)` offers
  `add` / `replace` for a picture whose locator names its source picture; `add` links the new file as a gallery
  picture after the others (undo removes the link), `replace` swaps the source picture's file in place (undo puts
  the old file back, the old `Picture` is the undo anchor). `apply` returns `{"ref"}` for an added link.
- Enrichment adapter: `list_pictures(subject_ref, channel)` (`[{ref, label, url, is_main}]`, main first, a picture
  linked twice listed once) and `picture(subject_ref, channel, picture_ref)` (`(bytes, mime)`; a ref that is not the
  product's → `LookupError`) — the AI studio animates a chosen picture in a video.
- Enrichment adapter: `subject_labels(refs, channel)` — `{sku: name}` of the SKUs that exist in the channel (name in
  the channel main language, else any; unknown SKUs left out) in two queries, for the enrichment `subjects/resolve/`
  endpoint (pasted SKUs in the AI studio).
- Enrichment adapter: field catalog for the AI studio — `describe_fields(channel, language)` lists the writable
  T9N text (`text` / `html`, `max_length` 255 for VARCHAR255_T9N) and select/multiselect features with labels in
  the language (fallback: channel main language) and at most 200 options (`options_truncated`), in three queries;
  `channel_languages(channel)` (main language first) and `make_locator(field_key, channel, language)` (language
  `None` for selects).
- Enrichment adapter: `attribute_value` reads, applies and reverts select (`{"option"}`) and multiselect
  (`{"options"}`) values; option idxs are validated against the feature (unknown → `ValueError`, nothing
  written), snapshots are sorted for drift checks, and writes on an inheriting secondary channel are marked
  overridden (`"*"`).
- Enrichment adapter: SEO text fields (`is_seo`, `meta_title`, `meta_description`) are catalogued as plain `text`
  capped at 255; `url_key`, `canonical_url` and `og_image` are not writable (absent from the catalog,
  `make_locator` raises); `apply` refuses to clear an inherited select on a secondary channel (the change would
  be silently refilled by materialisation).
- Enrichment adapter: `attribute_value` writes are refused (`ValueError`, nothing written) for a feature outside
  the product's feature set (system features always apply) and for a translatable feature whose locator has no
  language (the language is lowercased); the inherited-select guard and the `overridden_langs` marker follow the
  materialisation rules (channel `inheritance_enabled`, feature `exclude_from_inheritance`).
- Enrichment adapter: `field_key(locator)` (inverse of `make_locator`) so the bus finds the catalog entry of a
  PIM locator (None for `picture_alt` and `video` locators); the adapter passes the enrichment adapter
  conformance kit for text, select, multiselect and video targets. The kit is not released yet, so
  `tests/test_enrichment_conformance.py` skips unless it is installed by hand
  (`uv pip install -e ../entirius-django-enrichment`); `entirius-django-enrichment>=2.3.0` joins the `test`
  extra once released.
- Enrichment adapter: `category_of(subject_ref, channel=None)` returns the product's first category (by
  `position`, `pk`) as the memory ref `category:<idx>`, so a category SEO brief is reused by the other products of
  that category.
- Enrichment adapter: `apply` refuses `attribute_value` proposals for `url_key`, `canonical_url` and `og_image`
  (`ValueError`, nothing written) whatever built the locator — previously only the catalog and `make_locator`
  kept them out; `revert` can still restore a snapshot.

## 3.4.0 — 2026-10-12

- Access: the module declares its own access areas on its AppConfig and its admin views (copied from the
  entirius-django-access defaults; behaviour unchanged).
- OpenAPI: the quality-gap findings list and the `gaps/recompute/`, `gaps/status/` and `gaps/settings/` operations
  carry the `Quality Gaps` tag (they fell back to the default tag); the product-list pagination example uses
  `https://api.example.com`. Metadata only.

### Security

- File and picture upload: the temporary file takes only the sanitised extension of the uploaded name (ASCII
  letters, digits and dots, at most 16 characters) instead of the whole name, so path separators in a name
  never reach the temp file's path (such a name failed the upload with an unhandled error). The stored file, its type and `original_file_name` are unchanged.

## 3.3.1 — 2026-09-30

- **Security fix: the legacy `/api-viewer/pim/` routes are staff-only.** All 11 routes answered without
  authentication, including a `csrf_exempt` PUT on `…/attributes/<attr_idx>/extension/` that overwrote
  `Attribute.extension` for anyone. Every route now requires a Bearer JWT of a staff or superuser account
  (the admin API's rule): no or invalid token → 401, a non-staff user → 403. Callers of these routes must
  send a staff token; the v2 admin API (`/api/pim/v2/admin/`) is the supported way.

## 3.3.0 — 2026-09-30

- **Required per feature set.** New nullable `FeatureInFeatureSet.is_required` (migration `0063`):
  `null` inherits `Feature.is_required`, `true`/`false` overrides it for that set only. Effective flag:
  `FeatureInFeatureSet.effective_is_required`, `FeatureInFeatureSet.objects.effective_required()`. An
  override on a SYSTEM-scope feature is rejected (`ValueError`, 400 in the API); SYSTEM features flagged
  required apply to every set. New services in `feature_set_service`: `get_required_features`,
  `required_feature_idxs_by_set`, `set_feature_required_override`; `bulk_add_features_to_set` accepts
  `is_required`; reorder leaves the override alone. The customization reader
  (`get_filtered_attributes`) uses the effective flag. Docs: `docs/required-features.md`. Reported in #10.
- **Enforcement on create, off by default.** `create_product(..., enforce_required=None)`; `None` reads
  `PIM_ENFORCE_REQUIRED_ON_CREATE` (default `False`) at call time. A create that leaves a required feature
  without a value that would be stored raises `RequiredFeaturesMissingError` (new `django_pim.exceptions`,
  not a `ValueError`; carries `feature_set_idx` and sorted `missing_feature_idxs`) before anything is written.
  Attribute handling is split into a plan step and a write step so the check sees what will be stored;
  `find_missing_required(feature_set, attributes)` is the public helper. Create only: updates are not
  re-checked. Reported in #11.
- **Strict create, off by default.** `create_product(..., strict=None)` / `PIM_STRICT_CREATE`: refuse with
  `UnresolvedAttributesError` (not a `ValueError`) when the payload names an unknown feature, an unknown or
  foreign option, or an unknown category, instead of silently dropping it.
- **Admin API.** Features-in-set responses gain `is_required` (effective) and `is_required_override` (raw);
  bulk-add entries accept `is_required`; new `PATCH feature-sets/{idx}/features/{feature_idx}/`
  (`{"is_required": true|false|null}`) and `GET [{channel_idx}/]feature-sets/{idx}/required-features/`.
  Product create answers the v2 400 envelope with `REQUIRED_FEATURE_MISSING`, `UNRESOLVED_ATTRIBUTE` and
  `UNRESOLVED_CATEGORY` details. An unknown channel or feature set on create now answers 400 (was 404).
- **Fix:** `create_product` stored an empty row for LENGTH, MASS and TEMPERATURE values (the write step
  had no branch for them); `value_decimal` is now stored.
- **`pim-thumbs-generate`** exits non-zero (with a summary) when `THUMBS_CONFIG` is unset, no pictures were
  found, or every thumbnail failed; prints generated / present / failed counts; new `--missing-only`. The
  resizer creates `TMP_DIR` when absent instead of failing every thumbnail.
- **Units documented.** `RealProduct.weight` is in `DEFAULT_MASS_UNIT` (grams by default), `width`/`height`/`deep`
  in `DEFAULT_LENGTH_UNIT` (millimetres). The model comment pointed at a setting that never existed; schema
  descriptions and docs now state the units. No conversion, no data migration.
- Dev lock refreshed: sqlparse 0.6.0, soupsieve 2.10, djangorestframework 3.18.1 (open Dependabot alerts).
- **Upgrading:** run migration `0063`. Existing memberships inherit, so behaviour is unchanged.
  Enforcement and strict create are off by default and become the default in 4.0.0.

## 3.2.2 — 2026-09-28

- The category import (`DjangoPimRepository.category_update_or_create`) no longer replaces
  `description_t9n` wholesale on update: incoming descriptions are merged per locale and empty
  values are skipped, so an importer that sends `{locale: ""}` keeps descriptions entered in
  the admin. A non-empty incoming value still overwrites its locale.
- `Product.thumb_picture` read `picture.thumbs`, which does not exist (the reverse accessor
  from `Picture` is `picture_thumbs`), so the property raised `AttributeError` on every call and
  category listings returned `thumbnail_url: null`. Same slip as the `delete()` overrides fixed
  earlier in `models/picture.py` and `models/files.py`. Reported in #9.

## 3.2.1 — 2026-08-31

- `possible_duplicates[]` mirrors the django-lookup hit shape of 0.2.0: a new `match` field
  (`exact` | `similar` | `none`) and `similarity` now means relevance to the query as given (0-100),
  not the strongest dedup reason. `score` and `decision` are unchanged.

## 3.2.0 — 2026-08-26

- Lookup provider (`services/lookup_provider`) — exposes RealProduct items, display data and
  freshness specs to `entirius-django-lookup`, so the dedup engine can see the PIM catalog.
  Registered by the host through `LOOKUP_PROVIDERS`; the provider registry is the only switch.
- `services/lookup_bridge` — the seam the product create hook uses to ask "do we already have
  this?"; `possible_duplicates` in the product create response, tagged `source=create_hook`.
- Provider hardening: `Product` `post_save` declared so renames refresh the fingerprint,
  batched display calls, language consistency, graceful degradation, and query-cost fixes
  on the provider/bridge path.

## 3.1.0 — 2026-08-06

- Product variant groups.
- Bundle data services and the `option_titles` system feature.

## 3.0.0 — 2026-07-09

- Initial public release: the product catalog core — products, variants,
  categories, attributes, features, media, and channel scoping.
- Admin API v2 with Pydantic schemas and OpenAPI docs.
- Enrichment adapter implementation for the content-quality bus.
- Migrations squashed into a single initial migration for the Entirius epoch.

# Changelog

## Unreleased

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

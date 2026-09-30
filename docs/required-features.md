---
title: "Required Features"
description: "Per-feature-set required flags, opt-in enforcement on product create, and strict create."
---

`Feature.is_required` says a feature should have a value. Until 3.3.0 it was one flag per feature, so a
feature required on one set was required on every set that carried it, and nothing refused a create that
left it out. 3.3.0 adds a per-set override and two opt-in switches on create. Both switches are off by
default; they become the default in 4.0.0.

## Model

`FeatureInFeatureSet.is_required` is a nullable boolean on the membership.

| Value | Meaning |
|-------|---------|
| `null` (default) | Inherit `Feature.is_required` |
| `true` | Required in this set, whatever the feature says |
| `false` | Not required in this set, whatever the feature says |

The effective flag is the override when it is not `null`, otherwise the feature's flag. In code:
`FeatureInFeatureSet.effective_is_required`, and `FeatureInFeatureSet.objects.effective_required()` for the
same rule in SQL.

Example: `voltage` is required on a battery set and optional on a cable set. Mark the feature required, then
set the cable membership to `false`. Or leave the feature optional and set the battery membership to `true`.
Both work; pick the one with fewer exceptions.

Detaching a feature from a set deletes the membership, and the override with it. Re-adding starts at `null`.
Reordering never touches the override.

## System features

SYSTEM-scope features are implicit in every set (see [Feature Scope](./feature-scope/)), so they have no
per-set say:

- An override on a SYSTEM feature is rejected: `ValueError` in `FeatureInFeatureSet.save()`, **400** in the API.
- A SYSTEM feature with `is_required=true` is required in every set. Its membership row, if one exists, is
  ignored for this purpose.

## The required set of a feature set

The union of:

- memberships whose effective flag is `true` (SYSTEM rows excluded), and
- SYSTEM features with `is_required=true`.

| Function (`services/feature_set_service.py`) | Returns |
|---|---|
| `get_required_features(feature_set_idx)` | `list[(Feature, source)]`, system features first, then memberships by position |
| `required_feature_idxs_by_set()` | `{feature_set_idx: [feature_idx, ...]}`, every set present, lists sorted, system features included |
| `set_feature_required_override(feature_set_idx, feature_idx, value)` | The membership; `value` is `True`, `False` or `None` |

`source` is `"system"`, `"feature"` (inherited flag) or `"feature_set"` (override `true`).

## Enforcement on create

`create_product(..., enforce_required=None)`. `None` reads the Django setting
`PIM_ENFORCE_REQUIRED_ON_CREATE` at call time (default `False`); an explicit bool wins.

When on, a create that would leave a required feature without a stored value raises
`RequiredFeaturesMissingError` (`django_pim.exceptions`) and writes nothing: no `RealProduct`, no `Product`,
no attributes. It carries `feature_set_idx` and `missing_feature_idxs` (sorted). It is **not** a `ValueError`
subclass: callers commonly treat any `ValueError` from `create_product` as "duplicate SKU".

Order inside `create_product`: channel and feature set lookup, duplicate SKU (`ValueError`), attribute plan,
strict check, required check, write.

### What counts as supplied

The check runs on the plan the write step will follow, so only values that will actually be stored count.
These do **not** count:

- an unknown feature idx;
- an empty value (`""`, whitespace, an all-blank translated text, an empty JSON object, `null`);
- a value under the wrong key for the feature type (`value_txt` sent for a DECIMAL feature);
- a SELECT or MULTISELECT option that does not exist, or belongs to another feature;
- a SELECT or MULTISELECT key sent as `null` or an empty list (that is a clear signal).

These **do** count: `value_bool: false` and `value_decimal: "0"`. Same emptiness rule as the gap checks.

`find_missing_required(feature_set, attributes)` in `services/product_service.py` applies the same rule
without creating anything and returns the sorted missing feature idxs.

### Create only

Updates are not re-checked. `update_product` and the CSV importer's update path accept what they accepted
before; a product can lose a required value later. Checking on update needs a decision about partially
filled catalogues that 3.3.0 does not make.

### Why not a GapDefinition scope

Gap checks report what a product is missing after the fact, per channel and language, and their applicability
is feature-set membership by design. "Required" is a write-time contract of one set. Putting it into gaps
would mix a report with a refusal, and gap rules are tuned per channel while this is per set. The override
lives on the membership because that is where the set-specific facts already live (position, group).

## Strict create

`create_product(..., strict=None)`; `None` reads `PIM_STRICT_CREATE` (default `False`).

Default behaviour drops unresolvable input silently: an unknown feature idx, an option that does not exist or
belongs to another feature, an unknown category idx. With strict on, `create_product` raises
`UnresolvedAttributesError` (also not a `ValueError`) and writes nothing. It carries `unresolved_attributes`
(feature idxs, sorted) and `unknown_category_idxs` (sorted). Strict runs before the required check.

Values that are simply absent or sent under the wrong type are still ignored, not reported: the CMS sends a
whole feature set and expects untouched fields to stay untouched.

## Settings

| Setting | Default | Effect |
|---|---|---|
| `PIM_ENFORCE_REQUIRED_ON_CREATE` | `False` | Refuse creates that leave a required feature without a stored value |
| `PIM_STRICT_CREATE` | `False` | Refuse creates that reference unknown features, options or categories |

Both are read when `create_product` runs, so `override_settings` and runtime toggles work.

## Admin API

- `GET feature-sets/{idx}/features/` (and the channel-scoped variant) and the bulk-add response carry
  `is_required` (effective) and `is_required_override` (raw).
- `POST feature-sets/{idx}/features/`: each entry accepts `is_required` (`true`, `false`, `null`/absent).
- `PATCH feature-sets/{idx}/features/{feature_idx}/` with `{"is_required": true|false|null}`; the key is required.
  Returns the `FeatureInSetResponse`. 400 for a SYSTEM feature, 404 when the set, feature or membership is missing.
- `GET feature-sets/{idx}/required-features/` (and `{channel_idx}/feature-sets/{idx}/required-features/`)
  returns `[{"feature": FeatureResponse, "source": "system" | "feature" | "feature_set"}]`.

Details in the [API Reference](./api-reference/).

### Error shapes on `POST {channel_idx}/products/`

Missing required features, one detail per feature, sorted:

```json
{
  "error": "VALIDATION_ERROR",
  "message": "Required features are missing.",
  "debug_id": "f7a2c3b8",
  "details": [
    {
      "field": "attributes.voltage",
      "location": "body",
      "issue": "REQUIRED_FEATURE_MISSING",
      "description": "Feature 'voltage' is required in feature set 'battery' and has no value."
    }
  ]
}
```

Strict create uses the same envelope with `issue: "UNRESOLVED_ATTRIBUTE"` (`field: "attributes.<feature_idx>"`)
and `issue: "UNRESOLVED_CATEGORY"` (`field: "category_idxs.<idx>"`).

An unknown channel or feature set answers 400 in the same envelope (`issue: "NOT_FOUND"`, field `channel_idx`
with `location: "path"`, or `feature_set_idx` with `location: "body"`), independently of both switches.
Before 3.3.0 these were 404.

## Upgrading to 3.3.0

Run migration `0063`. Existing memberships get `null`, so they inherit and behaviour is unchanged.
Enforcement and strict create are off; turn them on per environment once clients send complete payloads.

---
title: "Feature Scope"
description: "How PIM feature scopes work — SYSTEM protection, GLOBAL deprecation, and BUSINESS_UNIT as the default."
---

Features in PIM have a `scope` field that controls visibility, editability, and lifecycle.

## Scope Values

| Value | Name | Status | Description |
|-------|------|--------|-------------|
| 1 | SYSTEM | Protected | Reserved platform attributes. Cannot be created, deleted, or have type/scope/required changed via API. |
| 2 | GLOBAL | **Deprecated** | Legacy Magento concept. Migration 0056 converts to BUSINESS_UNIT. API rejects scope=2. |
| 3 | BUSINESS_UNIT | Default | Standard user-created attributes. Full CRUD via API and CMS. |

## SYSTEM Features

13 features are reserved as SYSTEM scope. They form the structural backbone of every product:

`name`, `description`, `short_description`, `url_key`, `badge`, `brand`, `subname`, `subname2`, `size_table`, `extension`, `meta_title`, `meta_description`, `rich_content`

Defined in `django_pim.settings.SYSTEM_FEATURES_IDXS`.

### Protection Matrix

| Operation | Allowed? | Details |
|-----------|----------|---------|
| Edit `name_t9n` (labels) | Yes | Translation labels are cosmetic |
| Edit `display_order` | Yes | Ordering is cosmetic |
| Edit visibility flags (`is_visible`, `is_filterable`, etc.) | Yes | Channel config flags |
| Edit `frontend_input_type`, `filter_type` | Yes | Storefront rendering hints |
| Change `scope` | No | Must stay SYSTEM |
| Change `feature_type` | No | Would break all existing ProductAttribute values |
| Change `is_required` | No | Structural flag |
| Delete | No | Would corrupt product data |
| Create with scope=1 | No | System features are managed by the import pipeline |

Product attribute **values** on SYSTEM features (e.g., a product's name or description) remain fully editable. The protection is on the Feature definition, not on per-product values.

### CMS Behavior

When editing a SYSTEM feature in the CMS:

- Info banner: "This is a system feature. Type, scope, and required status are locked."
- Feature type dropdown: disabled
- Scope dropdown: disabled, shows "System"
- `is_required` toggle: disabled (uses `prevent` prop)
- Delete button: hidden
- All other fields: editable as normal

### API Behavior

- `POST /api/pim/admin/features/` with `scope=1` returns **400** (blocked at schema level, `ge=2`)
- `PATCH` with `scope`, `feature_type`, or `is_required` on a SYSTEM feature returns **400**
- `DELETE` on a SYSTEM feature returns **400**
- `GET` response includes `is_system: true` flag

## GLOBAL Scope (Deprecated)

GLOBAL was inherited from Magento ("shared across all shops") but was never fully implemented in Volkanos:

- `Product.get_product_attributes()` only returns `scope=BUSINESS_UNIT`, making GLOBAL features invisible in product editing
- The CSV importer defaulted unknown scopes to GLOBAL, silently creating invisible features
- Matrix/Cynthia `copy_features()` includes GLOBAL features (via `.exclude(scope=SYSTEM)`), but they never appear in product editing

### Migration Path

1. **Data migration 0056** converts all existing GLOBAL features to BUSINESS_UNIT
2. **API blocks scope=2** on create and update (service layer raises ValueError)
3. **CMS hides GLOBAL** from the scope dropdown on feature edit (only shows BUSINESS_UNIT)
4. **CSV importer** maps `"global"` to BUSINESS_UNIT, defaults unknown scopes to BUSINESS_UNIT

### CSV Import Fix

Before the fix, `discover_scope()` in `config_features_importer.py` defaulted to `FeatureScopeEnum.GLOBAL` for unrecognized scope values. Now defaults to `FeatureScopeEnum.BUSINESS_UNIT`.

## Cross-Module Behavior

| Module | How scope is used |
|--------|-------------------|
| **django-pim** | Feature model, admin API, service layer protection |
| **django-matrix** | `copy_features()` excludes SYSTEM, copies everything else |
| **django-cynthia** | `copy_features()` excludes SYSTEM, copies everything else |
| **django-pim-csv** | `discover_scope()` maps CSV text to enum, SYSTEM features detected by idx |

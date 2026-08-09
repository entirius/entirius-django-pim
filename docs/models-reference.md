---
title: Models Reference
description: Field-level inventory of django-pim ORM models.
---

Complete field-level inventory of all 37 ORM models in `src/django_pim/models/`.

---

## Enums

### FeatureTypeEnum (`models/feature.py`)

| Value | Name | Label | Storage field |
|-------|------|-------|---------------|
| 0 | UNKNOWN | Unknown | `value_txt` |
| 1 | BOOL | Bool | `value_bool` |
| 2 | DECIMAL | Decimal | `value_decimal` |
| 3 | VARCHAR255 | Varchar 255 | `value_txt` |
| 4 | VARCHAR255_T9N | Varchar 255 t9n | `value_txt_t9n` |
| 5 | TEXT | Text | `value_txt` |
| 6 | TEXT_T9N | Text t9n | `value_txt_t9n` |
| 7 | SELECT | Select | `attribute` (FK) |
| 8 | MULTISELECT | Multiselect | `attribute` (FK, multiple rows) |
| 9 | JSON | Json | `value_json` |
| 10 | DATETIME | Datetime | `value_datetime` |
| 11 | JSON_T9N | Json t9n | `value_json` |
| 12 | TEMPERATURE | Temperature | `value_decimal` (base unit) |
| 13 | LENGTH | Length | `value_decimal` (base unit) |
| 14 | MASS | Mass | `value_decimal` (base unit) |

### FeatureScopeEnum (`models/feature.py`)

| Value | Name | Label |
|-------|------|-------|
| 1 | SYSTEM | system |
| 2 | GLOBAL | global |
| 3 | BUSINESS_UNIT | business unit |

### FrontendInputTypeEnum (`models/feature.py`)

| Value | Name | Label |
|-------|------|-------|
| 0 | DEFAULT | Default |
| 1 | SELECT_SWATCH_VISUAL | Swatch_Visual |
| 2 | SELECT_SWATCH_TEXT | Swatch_Text |
| 3 | DROPDOWN | dropdown |
| 4 | DROPDOWN_WITH_PRICE | dropdown_with_price |
| 5 | PALETTE_COLOR | palette_color |
| 6 | SLIDER | slider |
| 7 | BOOLEAN | boolean |
| 8 | RADIO | radio |

Note: SWATCH types are only valid when `feature_type` is SELECT or MULTISELECT -- enforced in `Feature.save()`.

### FilterTypeEnum (`models/feature.py`)

| Value | Name | Label |
|-------|------|-------|
| 0 | DEFAULT | Default |
| 1 | SELECT_SWATCH_IMAGE | Swatch_Image |
| 2 | SELECT_SWATCH_TEXT | Swatch_Text |
| 3 | SLIDE | Slide |
| 4 | BOOLEAN | Boolean |
| 5 | RADIO_TEXT | Radio_Text |

### ProductClassEnum (`models/product.py`)

| Value | Name | Child model |
|-------|------|-------------|
| 0 | ProductBase | `Product` itself |
| 1 | ProductSimple | `ProductSimple` (MTI) |
| 2 | ProductConfigurable | `ProductConfigurable` (MTI) |
| 3 | ProductBundle | `ProductBundle` (MTI) |
| 4 | ProductCustom | `ProductCustom` (MTI) |

### ProductVisibilityEnum (`models/product.py`)

| Value | Name | Label |
|-------|------|-------|
| 0 | UNKNOWN | Unknown |
| 1 | NOT_VISIBLE_INDIVIDUALLY | Not visible individually |
| 2 | CATALOG | Catalog |
| 3 | SEARCH | Search |
| 4 | CATALOG_AND_SEARCH | Catalog and search |

### KindOfProductEnum (`models/real_product.py`)

| Value | Name | Label |
|-------|------|-------|
| 0 | ProductPhysical | Product Physical |
| 1 | ProductVirtual | Product Virtual |

### PictureRoleEnum (`models/product_picture.py`)

| Value | Name | API label |
|-------|------|-----------|
| 0 | UNKNOWN | unknown |
| 1 | MAIN | main |
| 2 | GENERAL | general |
| 3 | VARIANT | variant |
| 4 | ANGLE | angle |

### VideoRoleEnum (`models/product_video.py`)

| Value | Name | API label |
|-------|------|-----------|
| 0 | UNKNOWN | unknown |
| 1 | MAIN | main |
| 2 | VARIANT | variant |

### VideoSource (`models/video.py`)

TextChoices (string values):

| Value | Label |
|-------|-------|
| `"youtube"` | YouTube |
| `"vimeo"` | Vimeo |
| `"unknown"` | Unknown |

### FileRoleEnum (`models/files.py`)

| Value | Name | Label |
|-------|------|-------|
| 0 | UNDEFINED | Undefined File Type |
| 1 | PICTURE | Picture File Type |
| 2 | PDF | PDF File Type |
| 3 | DOC | Document File Type |
| 4 | VIDEO | Video File Type |

### ProductLinkTypeEnum (`models/product_links.py`)

| Value | Name | Label |
|-------|------|-------|
| 0 | UNKNOWN | Unknown |
| 1 | RELATED | Related |
| 2 | CROSSSELL | Crosssell |
| 3 | UPSELL | Upsell |
| 4 | NAVIGATION | Navigation |

### AttributeModifierTypeEnum (`models/attribute.py`)

| Value | Name | Label |
|-------|------|-------|
| 1 | UNKNOWN | unknown |
| 2 | VALUE | value |
| 3 | EXCLUDE | exclude |
| 4 | COLOR_HASH_INTERSECTION | color_hash_intersection |
| 5 | DEFAULT | default |
| 6 | COERCE | coerce |

### SectionTypeEnum (`models/product_bundle/bundle_link.py`)

| Value | Name | Label |
|-------|------|-------|
| 0 | INCLUDED_PRODUCTS | Included Products |

### PictureThumb.TransformMethod (`models/picture_thumb.py`)

TextChoices (string values):

| Value | Label |
|-------|-------|
| `"resize ratio, white"` | Resize ratio safe, white bg |
| `"resize ratio, black"` | Resize ratio safe, black bg |
| `"resize ratio, pink"` | Resize ratio safe, pink bg |
| `"resize ratio, transparent"` | Resize ratio safe, transparent bg |
| `"fill and crop, white"` | Fill and crop, white bg |
| `"fill and crop, black"` | Fill and crop, black bg |
| `"fill and crop, pink"` | Fill and crop, pink bg |
| `"fill and crop, transparent"` | Fill and crop, transparent bg |
| `"remove background experimental"` | Remove background experimental |
| `"remove background experimental v2"` | Remove background experimental_v2 |

### PictureThumb.ImageFormat (`models/picture_thumb.py`)

| Value | Label |
|-------|-------|
| `"png"` | png |
| `"webp"` | webp |
| `"jpg"` | jpg |
| `"gif"` | gif |

---

## Core Product Models

### RealProduct (`models/real_product.py`)

Shared record across all channels. One `RealProduct` per SKU, referenced by multiple `Product` rows (one per channel).

**Table:** `django_pim_realproduct`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `sku` | CharField(128) | No | No | -- | Validated by `validate_sku()` on save |
| `ean` | CharField(16) | Yes | Yes | NULL | `db_index=True`; validated by `validate_ean()` unless `ignore_validate_ean=True` |
| `kind_of_product` | PositiveSmallIntegerField | No | No | 0 (Physical) | `KindOfProductEnum` |
| `weight` | DecimalField(12,2) | Yes | Yes | NULL | Unit defined by `settings.PIM_weight_UNIT` |
| `width` | DecimalField(12,2) | Yes | Yes | NULL | Unit defined by `settings.PIM_DIMENSIONS_UNIT` |
| `height` | DecimalField(12,2) | Yes | Yes | NULL | Unit defined by `settings.PIM_DIMENSIONS_UNIT` |
| `deep` | DecimalField(12,2) | Yes | Yes | NULL | Unit defined by `settings.PIM_DIMENSIONS_UNIT` |
| `updated_at` | DateTimeField | No | No | auto_now | Updated on every save |

**Manager:** `EnhanceManager` (from `django_utils`)

**Unique constraints:**

| Constraint name | Fields | Type |
|-----------------|--------|------|
| `unique_real_product_sku` | `Lower(sku)` | UniqueConstraint (case-insensitive) |

**Indexes:**

| Index name | Fields |
|------------|--------|
| `idx_realproduct_sku_lower` | `Lower(sku)`, `id` |

**Behavior in `save()`:**
- Calls `validate_sku(self.sku)` always.
- Calls `validate_ean(self.ean)` unless `ignore_validate_ean=True` is passed.

**Properties:**
- `kind_of_product_name` -- human label for `kind_of_product` integer.

**Reverse relations:**
- `products` -- all `Product` instances in all channels sharing this SKU.
- `real_product_modifier_custom` -- `AttributeModifier` records scoped to this real product.

---

### Product (`models/product.py`)

Channel-scoped product record. One per `(RealProduct, Channel)` pair. Acts as the base for all product subtypes via Django multi-table inheritance (MTI).

**Table:** `django_pim_product`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `product_class` | SmallIntegerField | No | No | 0 (ProductBase) | `ProductClassEnum`; `db_index=True` |
| `real_product` | ForeignKey → RealProduct | No | No | -- | CASCADE; `related_name="products"` |
| `shop` | ForeignKey → Channel | No | No | -- | CASCADE; `related_name="products"` |
| `feature_set` | ForeignKey → FeatureSet | No | No | -- | CASCADE; `related_name="products"` |
| `categories` | ManyToManyField → ProductCategory | Yes | Yes | -- | Through `ProductInCategory`; `related_name="products"` |
| `visibility` | PositiveSmallIntegerField | No | No | 0 (UNKNOWN) | `ProductVisibilityEnum` |
| `magento_pk` | IntegerField | Yes | Yes | NULL | Legacy Magento ID |
| `updated_at` | DateTimeField | Yes | Yes | NULL | Manual; not auto_now |
| `is_enabled` | BooleanField | No | No | False | |
| `db_created` | DateTimeField | No | No | auto_now_add | |
| `db_modified` | DateTimeField | No | No | auto_now | |

**Manager:** `ProductManager(EnhanceManager)` with custom `ProductQuerySet`.

**QuerySet methods:**

| Method | Description |
|--------|-------------|
| `catalog_visible()` | Filters `is_enabled=True`, active categories, visibility in CATALOG/CATALOG_AND_SEARCH |
| `catalog_filterable()` | Same as above, plus includes simple subproducts whose configurable parent is visible |

**Manager methods (proxy to QuerySet):**

| Method | Description |
|--------|-------------|
| `catalog_visible()` | Same as QuerySet method |
| `catalog_filterable()` | Same as QuerySet method |

**Unique constraints:**

| Constraint | Fields | Notes |
|------------|--------|-------|
| `unique_together` | `(real_product, shop)` | One Product per channel per RealProduct |

**Indexes:**

| Index name | Fields |
|------------|--------|
| `idx_product_realproduct` | `real_product`, `id` |

**Properties:**

| Property | Returns |
|----------|---------|
| `as_child` | The subtype instance (e.g., `ProductSimple`) or self if `ProductBase` |
| `product_class_name` | String label of product class |
| `visibility_name` | String label of visibility |
| `name` | Name in channel default language (falls back to `T9N_DEFAULT_LANG`, then SKU) |
| `name_t9n_json` | Raw `value_txt_t9n` JSON dict for the name attribute |
| `url_key` | URL key in `T9N_DEFAULT_LANG` |
| `thumb_picture` | First `Thumb` of the MAIN `Picture`, or None |
| `main_picture` | First MAIN `Picture`, or None |
| `main_product_picture` | First MAIN `ProductPicture`, or None |
| `general_pictures` | List of GENERAL `Picture` objects |
| `subproducts_pictures` | List of `Picture` objects from all subproducts |
| `sku` | Delegates to `real_product.sku` |

**Key methods:**

| Method | Description |
|--------|-------------|
| `name_lang(lang)` | Resolves name for given language with fallback |
| `url_key_lang(lang)` | Resolves URL key for given language |
| `description_lang(lang)` | Resolves description for given language |
| `short_description_lang(lang)` | Resolves short description for given language |
| `attribute_t9n(feature_idx, lang, scope)` | Generic t9n attribute resolver |
| `generate_url_key(lang, max_length, append_sku)` | Generates slug URL key from name |
| `generate_url_key_hashed(lang, max_length)` | Generates URL key with MD5 hash suffix |
| `get_product_attributes()` | Returns BUSINESS_UNIT scope non-UNKNOWN attributes |
| `get_product_attributes_values(lang)` | Returns dict `{feature_idx: value}` |
| `get_breadcrumb_list(lang)` | Redis-cached breadcrumb list |

**Reverse relations:**
- `products_attributes` -- `ProductAttribute` records.
- `product_in_category` -- `ProductInCategory` through records.
- `pictures` -- `ProductPicture` records.
- `videos` -- `ProductVideo` records.
- `products` (from `ProductFile`) -- `ProductFile` records.
- `product_prices` -- `ProductPrice` records.
- `product_links` -- `ProductLink` records (this product as source).
- `linked_products_links` -- `ProductLink` records (this product as target).
- `product_modifier_custom` -- `AttributeModifier` records scoped to this product.
- `product_attribute_custom` -- `ProductAttributeCustomImage` records.
- `product_attribute_images` -- `ProductAttributeImage` records.
- `configurable_links` -- `ConfigurableLink` records (subproduct side).

---

### ProductSimple (`models/product_simple/product_simple.py`)

**Inherits:** `Product` (MTI -- shares `django_pim_product` + own table `django_pim_productsimple`)

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `product_ptr` | OneToOneField → Product | No | No | -- | PK + parent link |
| `quantity` | PositiveIntegerField | No | No | 0 | Stock quantity |

**Behavior in `save()`:** Forces `product_class = ProductClassEnum.ProductSimple`.

---

### ProductConfigurable (`models/product_configurable/product_configurable.py`)

**Inherits:** `Product` (MTI -- adds no extra fields)

**Table:** `django_pim_productconfigurable`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `product_ptr` | OneToOneField → Product | No | No | -- | PK + parent link |

**Behavior in `save()`:** Forces `product_class = ProductClassEnum.ProductConfigurable`.

**Reverse relations:**
- `subproduct_links` -- `ConfigurableLink` records.

---

### ProductBundle (`models/product_bundle/product_bundle.py`)

**Inherits:** `Product` (MTI -- adds no extra fields)

**Table:** `django_pim_productbundle`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `product_ptr` | OneToOneField → Product | No | No | -- | PK + parent link |

**Behavior in `save()`:** Forces `product_class = ProductClassEnum.ProductBundle`.

**Methods:**

| Method | Returns | Notes |
|--------|---------|-------|
| `return_all_subproduct_for_bundle()` | QuerySet of `BundleLink` | All bundle items |
| `get_max_limit_bundle()` | `Decimal` or `None` | Reads `ProductAttribute` with `feature__idx="max_limit_bundle"` |
| `get_min_limit_bundle()` | `Decimal` or `None` | Reads `ProductAttribute` with `feature__idx="min_limit_bundle"` |

**Reverse relations:**
- `bundle_links` -- `BundleLink` records.

---

### ProductCustom (`models/product_custom/product_custom.py`)

**Inherits:** `Product` (MTI)

**Table:** `django_pim_productcustom`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `product_ptr` | OneToOneField → Product | No | No | -- | PK + parent link |
| `customization_feature_set` | ForeignKey → FeatureSet | Yes | Yes | NULL | CASCADE; defines which features drive customization options |

**Behavior in `save()`:** Forces `product_class = ProductClassEnum.ProductCustom`.

---

## Feature System

### Feature (`models/feature.py`)

Global feature/attribute definition (shared across all channels).

**Table:** `django_pim_feature`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `scope` | PositiveSmallIntegerField | No | No | 3 (BUSINESS_UNIT) | `FeatureScopeEnum` |
| `idx` | CharField(128) | No | No | -- | `unique=True`; validated by `validate_idx()` |
| `features_sets` | ManyToManyField → FeatureSet | Yes | Yes | -- | Through `FeatureInFeatureSet`; `related_name="features"` |
| `magento_idx` | CharField(26) | Yes | Yes | NULL | `unique=True`; auto-generated from `idx` if not set |
| `magento_pk` | IntegerField | Yes | Yes | NULL | Legacy Magento attribute ID |
| `name_t9n` | JSONField | No | No | `{}` | `{"en": "...", "pl": "..."}` |
| `is_required` | BooleanField | No | No | False | |
| `is_visible` | BooleanField | No | No | True | |
| `is_filterable` | BooleanField | No | No | False | |
| `is_searchable` | BooleanField | No | No | True | |
| `is_comparable` | BooleanField | No | No | False | |
| `is_for_customization` | BooleanField | No | No | False | Used for ProductCustom options |
| `extra_value` | JSONField | Yes | Yes | `{}` | Arbitrary extra metadata; may be language-keyed |
| `feature_type` | PositiveSmallIntegerField | No | No | 0 (UNKNOWN) | `FeatureTypeEnum` |
| `frontend_input_type` | PositiveSmallIntegerField | No | No | 0 (DEFAULT) | `FrontendInputTypeEnum` |
| `filter_type` | PositiveSmallIntegerField | No | No | 0 (DEFAULT) | `FilterTypeEnum` |
| `display_order` | PositiveSmallIntegerField | No | No | auto | SYSTEM=10, GLOBAL=90, BUSINESS_UNIT=110 if unset |

**Manager:** `FeatureManager(models.Manager)` (on-model manager, not the legacy `managers/feature.py`)

**On-model manager methods:**

| Method | Description |
|--------|-------------|
| `get_or_none(**kwargs)` | Returns instance or None |
| `get_scoped_feature(feature_idx)` | Returns feature by idx |
| `get_system_features()` | Returns SYSTEM scope features ordered by `display_order` |
| `get_shop_features(shop, system_features)` | Returns SYSTEM + BUSINESS_UNIT features |
| `availability_table(print_out)` | Prints ASCII table of all features |

**Unique constraints:**

| Field | Type |
|-------|------|
| `idx` | `unique=True` |
| `magento_idx` | `unique=True` |

**Indexes:**

| Index name | Fields | Includes |
|------------|--------|---------|
| `idx_feature_type_optimized` | `feature_type` | `id`, `idx` |

**Behavior in `save()`:**
- Ensures `name_t9n` is a plain dict (not a default dict).
- Validates `idx` format via `validate_idx()`.
- Validates `frontend_input_type` compatibility with `feature_type` (SWATCH requires SELECT/MULTISELECT).
- Auto-generates `magento_idx` from `idx` if None (max 26 chars, MD5 hash suffix if truncated).
- Validates system feature idxs are not reused for non-SYSTEM scope.
- Sets `display_order` from scope priority if not explicitly provided.

**Properties:**

| Property | Description |
|----------|-------------|
| `scope_name` | String label of scope |
| `feature_type_name` | String label of feature type |
| `frontend_input_type_name` | String label of frontend input type |
| `filter_type_name` | String label of filter type |
| `name` | Name in `T9N_DEFAULT_LANG`, falls back to `idx` |

**Key methods:**

| Method | Description |
|--------|-------------|
| `name_lang(lang)` | Resolves name for language with fallback to `T9N_DEFAULT_LANG`, then `idx` |
| `get_cls_unit_conversion()` | Returns `(default_unit, model_unit)` for TEMPERATURE/LENGTH/MASS types |
| `get_extra_value_lang(language)` | Returns language-resolved `extra_value` dict |

**Reverse relations:**
- `feature_in_feature_set` -- `FeatureInFeatureSet` through records.
- `attributes` -- `Attribute` records belonging to this feature.
- `products_attributes` -- `ProductAttribute` records.

---

### FeatureSet (`models/feature_set.py`)

Named set of features assigned to products. Determines which features a product can have.

**Table:** `django_pim_featureset`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `idx` | CharField(256) | No | No | -- | `unique=True`; validated by `validate_idx()` |
| `name` | CharField(256) | No | Yes | `""` | Human name |
| `desc` | TextField | No | Yes | `""` | Internal description |
| `magento_idx` | CharField(26) | Yes | Yes | NULL | Legacy Magento attribute set ID |
| `magento_pk` | IntegerField | Yes | Yes | NULL | Legacy Magento ID |
| `is_default` | BooleanField | No | No | False | Whether this is the default set |

**Manager:** `FeatureSetManager(models.Manager)` with `availability_table()` debug helper.

**Behavior in `save()`:** Validates `idx` via `validate_idx()`.

**Reverse relations:**
- `features` -- `Feature` objects (via `FeatureInFeatureSet` M2M).
- `feature_in_feature_set` -- `FeatureInFeatureSet` through records.
- `products` -- `Product` records using this set.

---

### FeatureInFeatureSet (`models/feature_set.py`)

Through table for the Feature <-> FeatureSet M2M with position ordering.

**Table:** `django_pim_featureinfeatureset`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `feature_set` | ForeignKey → FeatureSet | No | No | -- | CASCADE; `related_name="feature_in_feature_set"` |
| `feature` | ForeignKey → Feature | No | No | -- | CASCADE; `related_name="feature_in_feature_set"` |
| `position` | IntegerField | No | No | 500 | Display order within set |

**Manager:** `models.Manager()` (default)

**Unique constraints:**

| Constraint name | Fields |
|-----------------|--------|
| `unique_feature_in_feature_set` | `(feature, feature_set)` |

**Behavior in `save()`:** If `position == 500` (the default), auto-assigns to `max(existing_positions) + 1`, minimum 500.

---

### Attribute (`models/attribute.py`)

A selectable option value for a SELECT/MULTISELECT feature (e.g., "Red" for feature "color").

**Table:** `django_pim_attribute`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `feature` | ForeignKey → Feature | No | No | -- | CASCADE; `related_name="attributes"` |
| `idx` | CharField(128) | No | No | -- | Validated by `validate_idx()` |
| `extension` | JSONField | Yes | Yes | NULL | Arbitrary extra data |
| `magento_idx` | CharField(26) | Yes | Yes | NULL | Auto-generated from `idx` if None |
| `magento_pk` | IntegerField | Yes | Yes | NULL | Legacy Magento option ID |
| `name_t9n` | JSONField | No | No | `{}` | `{"en": "...", "pl": "..."}` |
| `display_order` | PositiveSmallIntegerField | No | No | 100 | Sort order within feature |
| `group` | ForeignKey → AttributesGroup | Yes | Yes | NULL | CASCADE; `related_name="attributes"` |

**Manager:** `models.Manager()` (default)

**Unique constraints:**

| Constraint | Fields |
|------------|--------|
| `unique_together[0]` | `(feature, idx)` |
| `unique_together[1]` | `(feature, magento_idx)` |

**Indexes:**

| Index name | Fields | Includes |
|------------|--------|---------|
| `idx_attr_feature_optimized` | `feature` | `id`, `idx` |

**Behavior in `save()`:**
- Ensures `name_t9n` is a plain dict.
- Validates `idx` via `validate_idx()`.
- Auto-generates `magento_idx` if None (max 26 chars with hash suffix).

**Properties:**
- `name` -- name in `T9N_DEFAULT_LANG`, falls back to `idx`.

**Key methods:**
- `name_lang(lang)` -- resolves name with fallback.

**Reverse relations:**
- `products_attributes` -- `ProductAttribute` records using this attribute.
- `pictures` -- `AttributePicture` records.
- `attributes_modifier_custom` -- `AttributeModifier` M2M.
- `product_attribute_custom_attr` -- `ProductAttributeCustomImage` M2M.
- `attribute_picture` -- `ProductAttributeImage` records.

---

### AttributeModifier (`models/attribute.py`)

Defines conditional modifications to available attributes for ProductCustom products (EXCLUDE, VALUE, DEFAULT, COERCE rules).

**Table:** `django_pim_attributemodifier`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `source_id` | FloatField | No | No | -- | ID from import source |
| `product` | ForeignKey → Product | Yes | Yes | NULL | CASCADE; `related_name="product_modifier_custom"` |
| `real_product` | ForeignKey → RealProduct | Yes | Yes | NULL | CASCADE; `related_name="real_product_modifier_custom"` |
| `feature` | ForeignKey → Feature | Yes | Yes | NULL | CASCADE; `related_name="feature_modifier_custom"` |
| `attributes` | ManyToManyField → Attribute | Yes | Yes | -- | `related_name="attributes_modifier_custom"` |
| `groups` | ManyToManyField → AttributesGroup | Yes | Yes | -- | `related_name="groups_modifier_custom"` |
| `feature_modified` | ForeignKey → Feature | Yes | Yes | NULL | CASCADE; `related_name="feature_modified"` |
| `attribute_modified` | ForeignKey → Attribute | Yes | Yes | NULL | CASCADE; `related_name="attributes_modified"` |
| `attribute_coerced` | ForeignKey → Attribute | Yes | Yes | NULL | CASCADE; `related_name="attributes_coerced"` |
| `modifier_type` | PositiveSmallIntegerField | No | No | 1 (UNKNOWN) | `AttributeModifierTypeEnum` |
| `value_modifier` | DecimalField(64,12) | Yes | Yes | 0 | Numeric modifier value |
| `csv_row_hash` | CharField(3000) | Yes | Yes | NULL | Import deduplication hash |

**Manager:** `AttributeModifierManager(models.Manager)` with custom `AttributeModifierQuerySet`.

**QuerySet methods:**

| Method | Description |
|--------|-------------|
| `filter_by_all_attributes(attributes)` | Modifier must have all given attributes |
| `filter_by_all_groups(groups)` | Modifier must have all given groups |
| `filter_by_all_possible_groups(possible_groups)` | All modifier groups must be within given list |
| `filter_by_all_possible_attributes(possible_attributes)` | All modifier attributes must be within given list |

**Manager methods:**

| Method | Description |
|--------|-------------|
| `create_or_update(...)` | Upserts modifier using composite match of all FK fields |
| `get_all_intersection_of_two_features(chosen_attributes)` | Yields color-hash intersection tuples for all COLOR_HASH_INTERSECTION modifiers |

---

### AttributesGroup (`models/attributes_group.py`)

Named cluster of `Attribute` records for grouping within SELECT features.

**Table:** `django_pim_attributesgroup`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `idx` | CharField(128) | No | No | -- | `unique=True` (added in migration 0048) |
| `name_t9n` | JSONField | No | No | `{}` | `{"en": "...", "pl": "..."}` |

**Manager:** `models.Manager()` (default)

---

## Category System

### ProductCategory (`models/product_category.py`)

Hierarchical category tree, scoped per channel. Supports arbitrary depth via self-referential FK.

**Table:** `django_pim_productcategory`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `shop` | ForeignKey → Channel | No | No | -- | CASCADE; `related_name="products_categories"` |
| `parent_category` | ForeignKey → self | Yes | Yes | NULL | CASCADE; `related_name="subcategories"` |
| `idx` | CharField(128) | No | No | -- | Validated by `validate_idx()` |
| `external_id` | CharField(128) | Yes | Yes | NULL | External system ID |
| `url_key_t9n` | JSONField | No | Yes | `{}` | `{"en": "slug", "pl": "slug"}` |
| `name_t9n` | JSONField | No | No | `{}` | Localized names |
| `description_t9n` | JSONField | No | No | `{}` | Localized descriptions |
| `meta_title_t9n` | JSONField | No | No | `{}` | SEO title per language |
| `meta_description_t9n` | JSONField | No | No | `{}` | SEO description per language |
| `tree_deep` | IntegerField | No | Yes | -- | `db_index=True`; auto-computed on save (0 = root) |
| `position` | IntegerField | Yes | Yes | NULL | `db_index=True`; sort order among siblings |
| `is_active` | BooleanField | No | No | False | |
| `is_in_menu` | BooleanField | No | No | False | |
| `rich_content` | JSONField | Yes | Yes | NULL | Arbitrary rich content blob |
| `extension` | JSONField | Yes | Yes | NULL | Arbitrary extension data |
| `db_created` | DateTimeField | No | No | auto_now_add | |
| `db_modified` | DateTimeField | No | No | auto_now | |

**Manager:** `ProductCategoryManager(models.Manager)`

**Manager methods:**

| Method | Description |
|--------|-------------|
| `get_shop_root_categories(shop)` | Returns categories with `tree_deep=0` for given channel |

**Unique constraints:**

| Constraint name | Fields |
|-----------------|--------|
| `Products_Categories_unique_idx` | `(shop, idx)` |

**Behavior in `save()`:**
- Converts JSON fields to plain dicts.
- Validates `idx` via `validate_idx()`.
- Validates `url_key_t9n` (each lang code must be 2 chars; url_key must pass `validate_url_key()`).
- Auto-computes `tree_deep` from parent chain (0 if root).

**Properties:**

| Property | Description |
|----------|-------------|
| `name` | Name in channel default language |
| `description` | Description in `T9N_DEFAULT_LANG` |
| `breadcrumb_path` | `" > "` joined path from root to this category |
| `has_childs` | Boolean, whether subcategories exist |
| `all_childs` | QuerySet of direct child categories |

**Key methods:**

| Method | Description |
|--------|-------------|
| `name_lang(lang, any_lang_if_missing)` | Resolves name with fallback |
| `description_lang(lang, any_lang_if_missing)` | Resolves description with fallback |
| `url_key_lang(lang)` | Returns URL key for language; auto-generates and saves if missing |
| `get_breadcrumb_list()` | Returns list of category instances from root to self |
| `idx_path()` | Returns list of idx strings from root to self |
| `url_path(lang)` | Returns list of url_key strings from root to self |

**Reverse relations:**
- `subcategories` -- child categories.
- `product_in_category` -- `ProductInCategory` records.
- `products` -- `Product` records (via M2M through `ProductInCategory`).
- `pictures` -- `ProductCategoryPicture` records.

---

### ProductInCategory (`models/product_in_category.py`)

Through table for the Product <-> ProductCategory M2M with position.

**Table:** `django_pim_productincategory`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `product` | ForeignKey → Product | No | No | -- | CASCADE; `related_name="product_in_category"` |
| `category` | ForeignKey → ProductCategory | No | No | -- | CASCADE; `related_name="product_in_category"` |
| `position` | IntegerField | Yes | Yes | 0 | Sort order within category |
| `updated_at` | DateTimeField | Yes | Yes | NULL | Set to `timezone.now()` on first save if None |

**Unique constraints:**

| Constraint name | Fields |
|-----------------|--------|
| `unique_product_category` | `(product, category)` |

**Behavior in `save()`:** Sets `updated_at = timezone.now()` if it is None.

---

## Configurable Links

### ConfigurableLink (`models/product_configurable/configurable_link.py`)

Links a `ProductConfigurable` to one of its variant `Product` records via a `ProductAttribute`.

**Table:** `django_pim_configurablelink`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `product_configurable` | ForeignKey → ProductConfigurable | No | No | -- | CASCADE; `related_name="subproduct_links"` |
| `subproduct_attribute` | ForeignKey → ProductAttribute | No | No | -- | CASCADE; `related_name="configurable_links"` |
| `subproduct` | ForeignKey → Product | No | No | -- | CASCADE; `related_name="configurable_links"` |

**Unique constraints:**

| Constraint | Fields |
|------------|--------|
| `unique_together` | `(product_configurable, subproduct_attribute)` |

---

## Bundle Models

### BundleLink (`models/product_bundle/bundle_link.py`)

Links a `ProductBundle` to a component `Product` with quantity and section grouping.

**Table:** `django_pim_bundlelink`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `product_bundle` | ForeignKey → ProductBundle | No | No | -- | CASCADE; `related_name="bundle_links"` |
| `subproduct` | ForeignKey → Product | No | No | -- | CASCADE; `related_name="bundle_sub_links"` |
| `quantity` | PositiveIntegerField | No | No | 1 | Number of units |
| `section` | ForeignKey → BundleSection | No | No | -- | CASCADE; `related_name="bundle_section"` |
| `order` | PositiveIntegerField | No | No | 1 | Sort order within section |
| `can_change_quantity` | BooleanField | No | No | True | Whether customer can adjust quantity |
| `is_default` | BooleanField | No | No | False | Whether included by default |
| `is_required` | BooleanField | No | No | False | Whether mandatory |

**Unique constraints:**

| Constraint | Fields |
|------------|--------|
| `unique_together` | `(product_bundle, subproduct)` |

---

### BundleSection (`models/product_bundle/bundle_link.py`)

Named section within a bundle (e.g., "Accessories", "Main").

**Table:** `django_pim_bundlesection`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `idx` | CharField(64) | No | No | -- | `unique=True` |
| `name` | JSONField | Yes | Yes | `{}` | Localized name `{"en": "...", "pl": "..."}` |
| `desc` | JSONField | Yes | Yes | `{}` | Localized description |
| `section_type` | PositiveSmallIntegerField | No | No | 0 (INCLUDED_PRODUCTS) | `SectionTypeEnum` |

**Methods:**
- `name_lang(lang)` -- resolves name with `T9N_DEFAULT_LANG` fallback; returns `idx` if empty.
- `desc_lang(lang)` -- resolves description with fallback.

---

## ProductAttribute

### ProductAttribute (`models/product_attribute.py`)

Stores the actual value of one feature for one product. MULTISELECT features use multiple rows (one per selected attribute).

**Table:** `django_pim_productattribute`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `product` | ForeignKey → Product | No | No | -- | CASCADE; `related_name="products_attributes"` |
| `feature` | ForeignKey → Feature | No | No | -- | CASCADE; `related_name="products_attributes"` |
| `attribute` | ForeignKey → Attribute | Yes | Yes | NULL | CASCADE; `related_name="products_attributes"`; used for SELECT/MULTISELECT |
| `value_bool` | BooleanField | Yes | Yes | NULL | For BOOL type |
| `value_decimal` | DecimalField(24,6) | Yes | Yes | NULL | For DECIMAL, TEMPERATURE, LENGTH, MASS types |
| `value_datetime` | DateTimeField | Yes | Yes | NULL | For DATETIME type |
| `value_txt` | TextField | Yes | Yes | NULL | For VARCHAR255, TEXT types |
| `value_txt_t9n` | JSONField | Yes | Yes | NULL | For VARCHAR255_T9N, TEXT_T9N types; `{"pl": "...", "en": "..."}` |
| `value_json` | JSONField | Yes | Yes | NULL | For JSON, JSON_T9N types |
| `updated_at` | DateTimeField | No | No | auto_now | |

**Manager:** `ProductAttributeManager(EnhanceManager)` (complex customization logic for ProductCustom)

**Unique constraints:**

| Constraint | Fields | Notes |
|------------|--------|-------|
| `unique_together` | `(product, feature, attribute)` | Allows multiple MULTISELECT rows with different attributes |

**Indexes:**

| Index name | Fields |
|------------|--------|
| `idx_productattribute_optimized` | `attribute`, `product` |

**Behavior in `save()`:**
- Calls `validate_feature()` -- checks attribute belongs to feature; checks feature belongs to product's feature_set (except SYSTEM scope).
- Calls `validate_values()` -- checks the correct value field is populated for the feature type.

**Key methods:**

| Method | Description |
|--------|-------------|
| `get_value(lang, langs)` | Returns type-appropriate value; unit conversion for TEMPERATURE/LENGTH/MASS |
| `validate_values()` | Raises `ValueError` if wrong value field is empty for feature type |
| `validate_feature()` | Raises `ValueError` if attribute does not match feature, or feature not in product's set |
| `get_value_name_by_feature_type(feature_type)` | Static; returns field name string for given type |

**Feature type to storage field mapping:**

| FeatureType | Storage field |
|-------------|--------------|
| BOOL | `value_bool` |
| DECIMAL | `value_decimal` |
| VARCHAR255 | `value_txt` |
| VARCHAR255_T9N | `value_txt_t9n` |
| TEXT | `value_txt` |
| TEXT_T9N | `value_txt_t9n` |
| SELECT | `attribute` (FK) |
| MULTISELECT | `attribute` (FK, multiple rows) |
| JSON | `value_json` |
| JSON_T9N | `value_json` |
| DATETIME | `value_datetime` |
| TEMPERATURE | `value_decimal` |
| LENGTH | `value_decimal` |
| MASS | `value_decimal` |
| UNKNOWN | `value_txt` |

---

## Media Models

### Picture (`models/picture.py`)

Deduplicated image storage. Images are SHA1-hashed; same image file stored once.

**Table:** `django_pim_picture`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `image` | HashedImageField | No | No | -- | `upload_to="image"`; not editable; auto-sets `height`/`width` |
| `sha1` | CharField(40) | Yes | Yes | NULL | `db_index=True`; `unique=True`; computed on first save |
| `width` | PositiveSmallIntegerField | Yes | Yes | NULL | Auto-set by `HashedImageField` |
| `height` | PositiveSmallIntegerField | Yes | Yes | NULL | Auto-set by `HashedImageField` |
| `original_file_name` | CharField(256) | Yes | Yes | NULL | |
| `db_created` | DateTimeField | No | No | auto_now_add | |

**Behavior in `save()`:** On first save (no `pk`), validates size > 0, computes SHA1 from file content.

**Behavior in `delete()`:** Deletes all related `Thumb` objects first, then self.

**Signal:** `post_delete` signal (`auto_delete_file_on_delete`) removes the image file from filesystem.

**Reverse relations:**
- `picture_thumbs` -- `PictureThumb` records.
- `products` -- `ProductPicture` records.
- `product_categories` -- `ProductCategoryPicture` records.
- `attributes` -- `AttributePicture` records.
- `downloads_urls` -- `PictureDownloadUrl` records.
- `product_attribute_picture` -- `ProductAttributeImage` records.
- `product_attribute_custom_picture` -- `ProductAttributeCustomImage` records.

---

### Thumb (`models/thumb.py`)

Deduplicated thumbnail storage. Same structure as `Picture` but for processed thumbnails.

**Table:** `django_pim_thumb`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `image` | HashedImageField | No | No | -- | `upload_to="thumb"` |
| `sha1` | CharField(40) | Yes | Yes | NULL | `unique=True`; computed on first save |
| `width` | PositiveSmallIntegerField | Yes | Yes | NULL | |
| `height` | PositiveSmallIntegerField | Yes | Yes | NULL | |
| `db_created` | DateTimeField | No | No | auto_now_add | |

**Behavior in `save()`:** Same SHA1 computation as `Picture`.

**Signal:** `post_delete` signal removes thumb file from filesystem.

**Note:** The `url` property raises `Exception` (not implemented; URL resolution is view-layer concern).

---

### PictureThumb (`models/picture_thumb.py`)

Maps a source `Picture` to a generated `Thumb` with transform parameters. Allows multiple thumbs per picture at different sizes/formats.

**Table:** `django_pim_picturethumb`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `picture` | ForeignKey → Picture | No | No | -- | CASCADE; `related_name="picture_thumbs"` |
| `thumb` | ForeignKey → Thumb | No | No | -- | CASCADE; `related_name="picture_thumbs"` |
| `width` | PositiveSmallIntegerField | Yes | Yes | NULL | Requested output width (may differ from actual thumb size) |
| `height` | PositiveSmallIntegerField | Yes | Yes | NULL | Requested output height |
| `transform_method` | CharField(34) | No | No | -- | `db_index=True`; `TransformMethod` choices |
| `out_format` | CharField(4) | No | No | -- | `db_index=True`; `ImageFormat` choices |
| `db_created` | DateTimeField | No | No | auto_now_add | |

**Unique constraints:**

| Constraint | Fields |
|------------|--------|
| `unique_together` | `(picture, thumb, width, height, transform_method, out_format)` |

**Properties:**
- `get_transform_method` -- returns `TransformMethod` enum member.
- `get_transform_method_name` -- returns human label.

---

### PictureDownloadUrl (`models/picture_download_url.py`)

URL-to-picture cache for deduplicating picture downloads.

**Table:** `django_pim_picturedownloadurl`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `picture` | ForeignKey → Picture | No | No | -- | CASCADE; `related_name="downloads_urls"` |
| `url` | CharField(384) | No | No | -- | `db_index=True`; `unique=True` |
| `db_created` | DateTimeField | No | No | auto_now_add | |

---

### ProductPicture (`models/product_picture.py`)

Associates a `Picture` with a `Product` for a specific role and optional language.

**Table:** `django_pim_productpicture`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `product` | ForeignKey → Product | No | No | -- | CASCADE; `related_name="pictures"` |
| `picture` | ForeignKey → Picture | No | No | -- | CASCADE; `related_name="products"` |
| `picture_role` | PositiveSmallIntegerField | No | No | 0 (UNKNOWN) | `PictureRoleEnum` |
| `language` | ForeignKey → Language | Yes | Yes | NULL | CASCADE; `related_name="product_pictures"`; NULL means all languages |
| `position` | IntegerField | No | Yes | 0 | |
| `alt_text_t9n` | JSONField | No | Yes | `{}` | Alt text per language |

**Unique constraints:**

| Constraint name | Fields | Condition |
|-----------------|--------|-----------|
| `unique_product_picture_main` | `(product, picture_role, language)` | `picture_role = MAIN` |
| `unique_product_picture_general` | `(product, picture, language)` | `picture_role = GENERAL` |
| `unique_product_picture_angle` | `(product, picture, language)` | `picture_role = ANGLE` |
| `unique_product_picture_variant` | `(product, picture, language)` | `picture_role = VARIANT` |

**Note:** One product can have only one MAIN picture per language. Multiple GENERAL/ANGLE/VARIANT pictures are allowed but the same `Picture` cannot repeat for the same role+language.

---

### ProductCategoryPicture (`models/product_category_picture.py`)

Associates a `Picture` with a `ProductCategory`.

**Table:** `django_pim_productcategorypicture`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `product_category` | ForeignKey → ProductCategory | No | No | -- | CASCADE; `related_name="pictures"` |
| `picture` | ForeignKey → Picture | No | No | -- | CASCADE; `related_name="product_categories"` |
| `picture_role` | PositiveSmallIntegerField | No | No | 0 (UNKNOWN) | `PictureRole` choices |
| `position` | IntegerField | Yes | Yes | 0 | |

**Unique constraints:**

| Constraint | Fields |
|------------|--------|
| `unique_together` | `(product_category, picture)` |

---

### AttributePicture (`models/attribute_picture.py`)

Associates a `Picture` with an `Attribute` (e.g., a swatch image for a color attribute).

**Table:** `django_pim_attributepicture`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `attribute` | ForeignKey → Attribute | No | No | -- | CASCADE; `related_name="pictures"` |
| `picture` | ForeignKey → Picture | No | No | -- | CASCADE; `related_name="attributes"` |

**Unique constraints:**

| Constraint name | Fields |
|-----------------|--------|
| `unique_attribute_picture` | `(attribute, picture)` |

---

### ProductAttributeImage (`models/product_attribute_image.py`)

Per-product attribute image override (e.g., a product-specific swatch color hash). Also stores a `color_hash` for intersection logic in `ProductAttributeManager`.

**Table:** `django_pim_productattributeimage`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `product` | ForeignKey → Product | Yes | Yes | NULL | CASCADE; `related_name="product_attribute_images"`; NULL = global |
| `attribute` | ForeignKey → Attribute | No | No | -- | CASCADE; `related_name="attribute_picture"` |
| `picture` | ForeignKey → Picture | Yes | Yes | NULL | CASCADE; `related_name="product_attribute_picture"` |
| `color_hash` | CharField(64) | Yes | Yes | NULL | Color matching hash for intersection logic |

**Unique constraints:**

| Constraint | Fields |
|------------|--------|
| `unique_together` | `(product, attribute)` |

**Behavior in `save()`:** On update, if `attribute_id` changed, deletes all `ProductAttributeCustomImage` records that reference the old attribute. On new create, also triggers `_clean_custom_images()`.

---

### ProductAttributeCustomImage (`models/product_custom/product_custom_image.py`)

Cached composite image generated by layering attribute-specific images over the product main picture for ProductCustom display.

**Table:** `django_pim_productattributecustomimage`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `product` | ForeignKey → Product | No | No | -- | CASCADE; `related_name="product_attribute_custom"` |
| `attributes` | ManyToManyField → Attribute | Yes | Yes | -- | `related_name="product_attribute_custom_attr"` |
| `picture` | ForeignKey → Picture | No | No | -- | CASCADE; `related_name="product_attribute_custom_picture"` |

**Manager:** `ProductAttributeCustomImageManager`

**Manager methods:**

| Method | Description |
|--------|-------------|
| `get_or_create_image(product, attributes)` | Returns existing or creates new combined image for given attribute combination |

**Methods:**
- `generate_combined_image()` -- uses PIL to layer `ProductAttributeImage` pictures over the main product picture; saves result as a new `Picture`.

---

## Video Models

### Video (`models/video.py`)

Stores an external video reference (YouTube/Vimeo URL).

**Table:** `django_pim_video`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `title` | CharField(256) | Yes | Yes | NULL | |
| `is_external` | BooleanField | No | No | True | |
| `source` | CharField(32) | No | No | `"unknown"` | `VideoSource` choices |
| `video_url` | URLField(256) | Yes | Yes | NULL | |
| `db_created` | DateTimeField | No | No | auto_now_add | |
| `db_modified` | DateTimeField | No | No | auto_now | |

**Behavior in `save()`:** Auto-detects `source` from URL (youtube/vimeo substring match) if source is `UNKNOWN` or empty.

---

### ProductVideo (`models/product_video.py`)

Associates a `Video` with a `Product` for a specific role and optional language.

**Table:** `django_pim_productvideo`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `product` | ForeignKey → Product | No | No | -- | CASCADE; `related_name="videos"` |
| `video` | ForeignKey → Video | No | No | -- | CASCADE; `related_name="products"` |
| `video_role` | PositiveSmallIntegerField | No | No | 0 (UNKNOWN) | `VideoRoleEnum` |
| `language` | ForeignKey → Language | Yes | Yes | NULL | CASCADE; `related_name="product_videos"`; NULL means all languages |
| `position` | IntegerField | No | Yes | 0 | |

**Unique constraints:**

| Constraint name | Fields | Condition |
|-----------------|--------|-----------|
| `unique_product_video_main` | `(product, video_role, language)` | `video_role = MAIN` |
| `unique_product_video_variant` | `(product, video, language)` | `video_role = VARIANT` |

---

## File Models

### Files (`models/files.py`)

Deduplicated file storage (PDF, DOC, VIDEO, PICTURE).

**Table:** `django_pim_files`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `file` | HashedFileField | No | No | -- | `upload_to="files"`; not editable |
| `file_category` | ForeignKey → FilesCategory | Yes | Yes | NULL | CASCADE; `related_name="product_file_category"` |
| `sha1` | CharField(40) | Yes | Yes | NULL | `db_index=True`; `unique=True` |
| `original_file_name` | CharField(256) | Yes | Yes | NULL | |
| `file_label` | CharField(256) | Yes | Yes | NULL | |
| `weight` | CharField(20) | Yes | Yes | NULL | File size in MB (stored as string) |
| `file_path` | CharField(512) | Yes | Yes | NULL | Original filesystem path |
| `file_type` | PositiveSmallIntegerField | No | No | 0 (UNDEFINED) | `FileRoleEnum` |
| `codec` | CharField(20) | Yes | Yes | NULL | Video codec (for VIDEO type) |
| `height` | PositiveSmallIntegerField | Yes | Yes | NULL | For images/videos |
| `width` | PositiveSmallIntegerField | Yes | Yes | NULL | For images/videos |
| `db_created` | DateTimeField | No | No | auto_now_add | |

**Behavior in `delete()`:** Deletes related thumbs before self.

**Reverse relations:**
- `files` -- `ProductFile` records.
- `doc_downloads_urls` -- `FilesDownloadUrl` records.

---

### FilesCategory (`models/files_category.py`)

Category label for grouping files (e.g., "manuals", "certificates").

**Table:** `django_pim_filescategory`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `name_t9n` | JSONField | No | No | `{}` | Localized category name |
| `code` | CharField(256) | No | No | -- | Machine identifier |
| `db_created` | DateTimeField | No | No | auto_now_add | |

---

### ProductFile (`models/product_file.py`)

Associates a `Files` record with a `Product`.

**Table:** `django_pim_productfile`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `product` | ForeignKey → Product | No | No | -- | CASCADE; `related_name="products"` |
| `file` | ForeignKey → Files | No | No | -- | CASCADE; `related_name="files"` |

**Unique constraints:**

| Constraint | Fields |
|------------|--------|
| `unique_together` | `(product, file)` |

---

### FilesDownloadUrl (`models/files_download_url.py`)

URL-to-file cache for deduplicating file downloads.

**Table:** `django_pim_filesdownloadurl`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `file` | ForeignKey → Files | No | No | -- | CASCADE; `related_name="doc_downloads_urls"` |
| `url` | CharField(384) | No | No | -- | `db_index=True`; `unique=True` |
| `db_created` | DateTimeField | No | No | auto_now_add | |

---

## Pricing

### ProductPrice (`models/product_price.py`)

Price record per product per currency. One row per `(product, currency)` pair.

**Table:** `django_pim_productprice`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `product` | ForeignKey → Product | No | No | -- | CASCADE; `related_name="product_prices"` |
| `currency` | ForeignKey → Currency | Yes | Yes | NULL | CASCADE; `related_name="product_prices"` |
| `price_brutto` | DecimalField(12,2) | Yes | Yes | NULL | Gross price |
| `special_price` | DecimalField(12,2) | Yes | Yes | NULL | Promotional price |
| `special_price_from` | DateTimeField | Yes | Yes | NULL | Special price start |
| `special_price_to` | DateTimeField | Yes | Yes | NULL | Special price end |

**Unique constraints:**

| Constraint | Fields |
|------------|--------|
| `unique_together` | `(product, currency)` |

**Properties:**
- `special_price_active` -- True if `special_price` is set and current datetime is within `[special_price_from, special_price_to]` range (None bounds are open).

---

## Links

### ProductLink (`models/product_links.py`)

Directional link between two products (related, crosssell, upsell, navigation).

**Table:** `django_pim_productlink`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `product` | ForeignKey → Product | No | No | -- | CASCADE; `related_name="product_links"` |
| `linked_product` | ForeignKey → Product | No | No | -- | CASCADE; `related_name="linked_products_links"` |
| `link_type` | PositiveSmallIntegerField | No | No | 0 (UNKNOWN) | `ProductLinkTypeEnum` |
| `position` | IntegerField | No | Yes | 1 | |
| `db_created` | DateTimeField | No | No | auto_now_add | |
| `db_modified` | DateTimeField | No | No | auto_now | |

**Unique constraints:**

| Constraint | Fields |
|------------|--------|
| `unique_together` | `(product, linked_product, link_type)` |

**Properties:**
- `link_type_name` -- string label of link type.

---

### ProductLinkToFeature (`models/product_link_to_feature.py`)

Optional feature assignment for NAVIGATION-type product links.

**Table:** `django_pim_productlinktofeature`

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `link` | ForeignKey → ProductLink | No | No | -- | CASCADE |
| `feature` | ForeignKey → Feature | No | No | -- | CASCADE |

**Behavior in `save()`:** Raises `Exception` if `link.link_type != NAVIGATION`.

---

## Channel

### Channel (`models/channel.py`)

Sales channel / store view. Central scope for all per-channel data.

**Table:** `django_pim_shop` (legacy table name preserved via `Meta.db_table`)

| Field | Type | Null | Blank | Default | Notes |
|-------|------|------|-------|---------|-------|
| `id` | AutoField | No | No | auto | PK |
| `idx` | CharField(128) | No | No | -- | `unique=True`; validated by `validate_idx()` |
| `name` | CharField(128) | No | No | `""` | `unique=True` |
| `default_language` | ForeignKey → Language | No | No | -- | PROTECT; `related_name="pim_default_channels"` |
| `default_currency` | ForeignKey → Currency | No | No | -- | PROTECT; `related_name="pim_default_channels"` |
| `languages` | ManyToManyField → Language | Yes | Yes | -- | `related_name="pim_channels"`; `db_table="django_pim_shop_languages"` |
| `currencies` | ManyToManyField → Currency | Yes | Yes | -- | `related_name="pim_channels"`; `db_table="django_pim_shop_currencies"` |

**Manager:** `ChannelManager(models.Manager)` with `availability_table()` debug helper.

**Behavior in `save()`:**
- Validates `idx` via `validate_idx()`.
- Automatically adds `default_language` to `languages` M2M.
- Automatically adds `default_currency` to `currencies` M2M.

**Methods:**
- `resolve_language(params)` -- returns `lang` from params dict, or channel default language iso2.
- `resolve_currency(params)` -- returns `currency` from params dict, or channel default currency iso3.

**Backward-compatible alias:** `Shop = Channel`, `ShopManager = ChannelManager` (defined in `shop.py` shim).

---

## Managers (Legacy)

The `managers/` directory contains stateful legacy utilities used by CSV importers and sync pipelines. These are plain Python classes with static methods, not Django model managers (`models.Manager` subclasses). The v2 Admin API does not use them; use `services/` instead.

| Module | Class | Key methods | Notes |
|--------|-------|-------------|-------|
| `managers/product.py` | `ProductManager` | `generate_sku_internal()`, `update_product()`, `delete()`, `get_product_features()` | Static methods; references legacy `sku_internal` field |
| `managers/feature.py` | `FeatureManager` | `generate_idx(name)`, `get_or_create_feature(...)`, `update_feature(...)` | Class-level `_cache_features` dict; most methods marked deprecated |
| `managers/category.py` | `CategoryManager` | `get_categories_in_el_tree_format()`, `get_categories_tree_as_list()`, `get_category_from_tree()`, `update_product_category()` | Redis-cached tree traversal (1h TTL) |
| `managers/attribute.py` | `AttributeManager` | `generate_idx(name)`, `get_or_create_attribute(...)`, `update_attribute(...)` | Class-level `_cache_attributes` dict; special char slug replacements |
| `managers/channel.py` | `ChannelManager` | `get_channel(idx)`, `get_or_create_channel(...)`, `update_channel(...)` | Class-level `_cache_channels` dict; `ShopManager = ChannelManager` alias |
| `managers/product_attribute.py` | `ProductAttributeManager` | `get_product_attribute(product, feature, attribute)`, `update_product_attribute(...)` | Handles MULTISELECT (returns QuerySet vs single instance) |
| `managers/picture.py` | `PictureManager` | `download_picture(url, sha1, ...)`, `get_picture(img_path, sha1)`, `get_picture_by_sha(sha1)` | HTTP/FTP download + dedup; CMYK validation |
| `managers/files.py` | `FilesManager` | `download_file(url, sha1, ...)`, `get_file(file_path, sha1)`, `get_file_by_sha(sha1)` | HTTP/FTP download; type detection by extension |
| `managers/product_simple/product_simple.py` | `ProductSimpleManager` | `get(sku_internal, ean)`, `get_or_create(sku_internal, feature_set)`, `update_product_quantity(product, quantity)` | References legacy `sku_internal` |
| `managers/product_configurable/product_configurable.py` | `ProductConfigurableManager` | `get(sku_internal, ean)`, `get_or_create(sku_internal, feature_set)`, `get_subproducts(product_configurable)` | References legacy `sku_internal` |
| `managers/product_custom/product_custom.py` | `ProductCustomManager` | `get(sku_internal, ean)`, `get_or_create(sku_internal, feature_set)` | References legacy `sku_internal` |

---

## Unique Constraints Summary

| Model | Field(s) | Constraint type | Name |
|-------|----------|-----------------|------|
| `RealProduct` | `Lower(sku)` | UniqueConstraint | `unique_real_product_sku` |
| `Product` | `(real_product, shop)` | `unique_together` | -- |
| `Feature` | `idx` | `unique=True` | -- |
| `Feature` | `magento_idx` | `unique=True` | -- |
| `FeatureSet` | `idx` | `unique=True` | -- |
| `FeatureInFeatureSet` | `(feature, feature_set)` | UniqueConstraint | `unique_feature_in_feature_set` |
| `Attribute` | `(feature, idx)` | `unique_together[0]` | -- |
| `Attribute` | `(feature, magento_idx)` | `unique_together[1]` | -- |
| `AttributesGroup` | `idx` | `unique=True` | Added migration 0048 |
| `AttributePicture` | `(attribute, picture)` | UniqueConstraint | `unique_attribute_picture` |
| `ProductAttribute` | `(product, feature, attribute)` | `unique_together` | Allows MULTISELECT multi-row |
| `ProductAttributeImage` | `(product, attribute)` | `unique_together` | -- |
| `ProductCategory` | `(shop, idx)` | UniqueConstraint | `Products_Categories_unique_idx` |
| `ProductInCategory` | `(product, category)` | UniqueConstraint | `unique_product_category` |
| `ProductPicture` | `(product, picture_role, language)` | UniqueConstraint (conditional) | `unique_product_picture_main` (MAIN only) |
| `ProductPicture` | `(product, picture, language)` | UniqueConstraint (conditional) | `unique_product_picture_general` (GENERAL) |
| `ProductPicture` | `(product, picture, language)` | UniqueConstraint (conditional) | `unique_product_picture_angle` (ANGLE) |
| `ProductPicture` | `(product, picture, language)` | UniqueConstraint (conditional) | `unique_product_picture_variant` (VARIANT) |
| `ProductCategoryPicture` | `(product_category, picture)` | `unique_together` | -- |
| `ProductVideo` | `(product, video_role, language)` | UniqueConstraint (conditional) | `unique_product_video_main` (MAIN only) |
| `ProductVideo` | `(product, video, language)` | UniqueConstraint (conditional) | `unique_product_video_variant` (VARIANT) |
| `Picture` | `sha1` | `unique=True` | SHA1 deduplication |
| `Thumb` | `sha1` | `unique=True` | SHA1 deduplication |
| `PictureDownloadUrl` | `url` | `unique=True` | -- |
| `PictureThumb` | `(picture, thumb, width, height, transform_method, out_format)` | `unique_together` | -- |
| `Files` | `sha1` | `unique=True` | -- |
| `FilesDownloadUrl` | `url` | `unique=True` | -- |
| `ProductFile` | `(product, file)` | `unique_together` | -- |
| `ProductPrice` | `(product, currency)` | `unique_together` | -- |
| `ProductLink` | `(product, linked_product, link_type)` | `unique_together` | -- |
| `ConfigurableLink` | `(product_configurable, subproduct_attribute)` | `unique_together` | -- |
| `BundleLink` | `(product_bundle, subproduct)` | `unique_together` | -- |
| `BundleSection` | `idx` | `unique=True` | -- |
| `Channel` | `idx` | `unique=True` | -- |
| `Channel` | `name` | `unique=True` | -- |

---

## System Features

System features (`scope=SYSTEM`) are auto-created from the fixture `pim-features-system.yaml` and the 13 idx constants defined in `settings.py`. PKs 1-6 are in the fixture; the remaining 7 are created programmatically by the CSV importer.

| PK | idx | feature_type | display_order | Notes |
|----|-----|-------------|---------------|-------|
| 1 | `name` | TEXT_T9N (6) | 1 | Product name; required=True |
| 2 | `short_description` | TEXT_T9N (6) | 2 | Short description |
| 3 | `description` | TEXT_T9N (6) | 3 | Full description |
| 4 | `url_key` | TEXT_T9N (6) | 4 | URL slug; is_visible=False |
| 5 | `size_table` | JSON (9) | 5 | Size chart JSON; is_visible=False |
| 6 | `rich_content` | JSON (9) | 6 | Rich content JSON; is_visible=False, is_searchable=False |
| -- | `badge` | -- | -- | Promotional badge |
| -- | `brand` | -- | -- | Brand name |
| -- | `subname` | -- | -- | Product subtitle |
| -- | `subname2` | -- | -- | Second subtitle |
| -- | `extension` | -- | -- | Extension data |
| -- | `meta_title` | -- | -- | SEO title |
| -- | `meta_description` | -- | -- | SEO meta description |

All system feature idxs are listed in `settings.SYSTEM_FEATURES_IDXS`. The `Feature.save()` method raises `AssertionError` if a non-SYSTEM feature attempts to use one of these reserved idxs.

---

## Django Admin Registration

All models are registered in `admin.py`. Key admin classes and notable configuration:

| Model | Admin class | Notable configuration |
|-------|------------|----------------------|
| `Channel` | `ChannelAdmin` | Search by `idx` |
| `RealProduct` | `RealProductAdmin` | `sku` readonly; search by sku/ean |
| `Product` | `ProductAdmin` | Autocomplete on `real_product`; search includes name via `value_txt_t9n` JSON lookup |
| `ProductSimple` | `ProductSimpleAdmin` | Adds `quantity` to list |
| `ProductConfigurable` | `ProductConfigurableAdmin` | Search by configurable links SKU |
| `ProductBundle` | `ProductBundleAdmin` | Search by bundle links SKU |
| `ProductCustom` | `ProductCustomAdmin` | Standard product fields |
| `Feature` | `FeatureAdmin` | Inline `FeatureInFeatureSet`; 12 bulk admin actions for toggling boolean flags |
| `Attribute` | `AttributeAdmin` | Filter by feature |
| `AttributeModifier` | `AttributeModifierAdmin` | Autocomplete on all FK/M2M fields; filtered by modifier_type, product, shop |
| `ProductAttribute` | `ProductAttributeAdmin` | Type-aware value display in list; dynamic t9n language fields in detail view |
| `ProductCategory` | `ProductCategoryAdmin` | `parent_category` readonly; ordered by `tree_deep`; thumbnail inline |
| `ProductPicture` | `ProductPictureAdmin` | Thumbnail preview; filter by role, language, shop, product_class |
| `Picture` | `PictureAdmin` | Thumbnail preview; sha1/image readonly |
| `PictureThumb` | `PictureThumbAdmin` | Before/after thumbnail preview; filter by transform_method, out_format |
| `ProductPrice` | `ProductPriceAdmin` | Product/currency readonly |
| `ConfigurableLink` | `ConfigurableLinkAdmin` | All fields readonly; shows subproduct feature idx |
| `BundleLink` | `BundleLinkAdmin` | Autocomplete on product_bundle, subproduct, section |
| `AttributesGroup` | `AttributesGroupAdmin` | Registered via `@admin.register` decorator |

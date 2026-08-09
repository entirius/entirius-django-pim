---
title: API Reference
description: Complete endpoint reference for the django-pim Admin API v2.
---

Full surface documentation for the PIM Admin API. Covers endpoint routes, query parameters, request/response schemas, and error codes.

**Base URL prefix:** `/api/pim/v2/admin/` (canonical) or `/api/pim/admin/` (legacy alias, same handlers)

**Authentication:** All endpoints require `JWTAuthentication` + `IsAdminUser` (`is_staff=True` or `is_superuser=True`). Pass token in header: `Authorization: Bearer <token>`.

**Pagination:** `AdminPageNumberPagination` -- `page_size=20`, `max_page_size=100`, `page_size_query_param="page_size"`, `page_query_param="page"`.

---

## Route Map

| Method | Path | Action |
|--------|------|--------|
| GET | `{channel_idx}/products/` | List products |
| POST | `{channel_idx}/products/` | Create product |
| GET | `{channel_idx}/products/{sku}/` | Retrieve product |
| PATCH | `{channel_idx}/products/{sku}/` | Update product |
| DELETE | `{channel_idx}/products/{sku}/` | Delete product |
| POST | `{channel_idx}/products/bulk/` | Bulk update products |
| GET | `{channel_idx}/categories/` | List categories |
| POST | `{channel_idx}/categories/` | Create category |
| GET | `{channel_idx}/categories/{idx}/` | Retrieve category |
| PATCH | `{channel_idx}/categories/{idx}/` | Update category |
| DELETE | `{channel_idx}/categories/{idx}/` | Delete category |
| GET | `features/` | List features (global) |
| POST | `features/` | Create feature |
| GET | `features/{idx}/` | Retrieve feature |
| PATCH | `features/{idx}/` | Update feature |
| DELETE | `features/{idx}/` | Delete feature |
| GET | `features/{idx}/attributes/` | List attributes for feature |
| GET | `{channel_idx}/features/` | List features (channel-scoped, read-only) |
| GET | `{channel_idx}/features/{idx}/` | Retrieve feature (channel-scoped) |
| GET | `{channel_idx}/features/{idx}/attributes/` | List attributes for feature (channel-scoped) |
| GET | `feature-sets/` | List feature sets (global) |
| POST | `feature-sets/` | Create feature set |
| GET | `feature-sets/{idx}/` | Retrieve feature set |
| PATCH | `feature-sets/{idx}/` | Update feature set |
| DELETE | `feature-sets/{idx}/` | Delete feature set |
| GET | `feature-sets/{idx}/features/` | List features in set |
| POST | `feature-sets/{idx}/features/` | Bulk add features to set |
| DELETE | `feature-sets/{idx}/features/` | Bulk remove features from set |
| GET | `{channel_idx}/feature-sets/` | List feature sets (channel-scoped, read-only) |
| GET | `{channel_idx}/feature-sets/{idx}/` | Retrieve feature set (channel-scoped) |
| GET | `{channel_idx}/feature-sets/{idx}/features/` | List features in set (channel-scoped) |
| GET | `attributes/` | List attributes |
| POST | `attributes/` | Create attribute |
| GET | `attributes/{feature_idx}/{idx}/` | Retrieve attribute |
| PATCH | `attributes/{feature_idx}/{idx}/` | Update attribute |
| DELETE | `attributes/{feature_idx}/{idx}/` | Delete attribute |
| GET | `attributes-groups/` | List attributes groups (global) |
| POST | `attributes-groups/` | Create attributes group |
| GET | `attributes-groups/{idx}/` | Retrieve attributes group |
| PATCH | `attributes-groups/{idx}/` | Update attributes group |
| DELETE | `attributes-groups/{idx}/` | Delete attributes group |
| GET | `{channel_idx}/attributes-groups/` | List attributes groups (channel-scoped, read-only) |
| GET | `{channel_idx}/attributes-groups/{idx}/` | Retrieve attributes group (channel-scoped) |

**Scope rules:**

- **Channel-scoped CRUD** (Products, Categories): all operations require `{channel_idx}` path param.
- **Global write + channel read** (Features, Feature Sets, Attributes Groups): create/update/delete on global routes; list/retrieve available on both global and `{channel_idx}/` routes.
- **Global only** (Attributes): composite key `{feature_idx}/{idx}`. No channel-scoped routes.

---

## Pagination Envelope

All list endpoints return:

```json
{
  "count": 150,
  "next": "http://localhost:8000/api/pim/v2/admin/en/products/?page=2",
  "previous": null,
  "results": [ ... ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `count` | `int` | Total items matching query |
| `next` | `str\|null` | URL to next page, null if last page |
| `previous` | `str\|null` | URL to previous page, null if first page |
| `results` | `list` | Items in the current page |

---

## Error Codes

| HTTP | Code condition |
|------|----------------|
| `400` | Pydantic/DRF validation failure, duplicate `idx`/`sku`, invalid parameter type, circular parent reference |
| `401` | No token or expired token |
| `403` | Valid token but `is_staff=False` and `is_superuser=False` |
| `404` | Channel, product, category, feature, feature set, or attribute not found |
| `500` | Unexpected server error |

Error body format:

```json
{"detail": "Human-readable message"}
```

---

## Products

All product endpoints are channel-scoped. Path parameter `{channel_idx}` is always required.

### Path Parameters

| Param | Type | Description |
|-------|------|-------------|
| `channel_idx` | `str` | Channel identifier (required on all product endpoints) |
| `sku` | `str` | Product SKU (required on retrieve, update, delete) |

### List Products

`GET {channel_idx}/products/`

**Query parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `search` | `str` | Filter by name or SKU (case-insensitive) |
| `is_enabled` | `bool` | Filter by enabled status. Accepts `true`/`1`/`yes` or `false`/`0`/`no` |
| `ordering` | `str` | Order by field. Examples: `name`, `-name`, `sku` |
| `page` | `int` | Page number |
| `page_size` | `int` | Items per page (max 100, default 20) |

**Response `200 ProductListResponse`:**

| Field | Type | Description |
|-------|------|-------------|
| `count` | `int` | Total matching products |
| `next` | `str\|null` | Next page URL |
| `previous` | `str\|null` | Previous page URL |
| `results` | `list[ProductResponse]` | See ProductResponse table |

**ProductResponse** (used in list results):

| Field | Type | Description |
|-------|------|-------------|
| `pk` | `int` | Primary key |
| `sku` | `str` | Stock Keeping Unit |
| `name` | `str` | Product name (default language) |
| `visibility` | `str` | Visibility label, e.g. `"Catalog and search"` |
| `is_enabled` | `bool` | Whether product is active |

**Status codes:** `200`, `400`, `401`, `403`, `404` (channel not found)

---

### Retrieve Product

`GET {channel_idx}/products/{sku}/`

**Response `200 ProductDetailResponse`:**

| Field | Type | Description |
|-------|------|-------------|
| `pk` | `int` | Primary key |
| `sku` | `str` | Stock Keeping Unit |
| `name` | `str` | Default language name |
| `name_t9n` | `dict` | Translated names, e.g. `{"en": "Laptop", "pl": "Laptop"}` |
| `description_t9n` | `dict` | Translated descriptions |
| `visibility` | `int` | Visibility enum value |
| `visibility_name` | `str` | Visibility label |
| `is_enabled` | `bool` | |
| `product_class` | `int` | Product class enum value |
| `product_class_name` | `str` | Product class label |
| `feature_set_idx` | `str` | Feature set identifier |
| `weight` | `str\|null` | Weight as decimal string |
| `width` | `str\|null` | Width as decimal string |
| `height` | `str\|null` | Height as decimal string |
| `deep` | `str\|null` | Depth as decimal string |
| `ean` | `str\|null` | EAN barcode |
| `kind_of_product` | `int` | 0=Physical, 1=Virtual |
| `categories` | `list[ProductCategoryBriefResponse]` | Assigned categories |
| `attributes` | `list[ProductAttributeValueResponse]` | Attribute values |

**ProductCategoryBriefResponse:**

| Field | Type | Description |
|-------|------|-------------|
| `pk` | `int` | Category primary key |
| `idx` | `str` | Category identifier |
| `name` | `str` | Category display name |
| `breadcrumb_path` | `str` | e.g. `"Root > Electronics"` |

**ProductAttributeValueResponse:**

| Field | Type | Description |
|-------|------|-------------|
| `feature_idx` | `str` | Feature identifier |
| `feature_name` | `str` | Resolved display name |
| `feature_type` | `int` | Feature type enum value |
| `feature_type_name` | `str` | Human label |
| `value_bool` | `bool\|null` | Set for BOOL features |
| `value_decimal` | `str\|null` | Set for DECIMAL/TEMPERATURE/LENGTH/MASS features |
| `value_txt` | `str\|null` | Set for VARCHAR255/TEXT features |
| `value_txt_t9n` | `dict\|null` | Set for VARCHAR255_T9N/TEXT_T9N features |
| `value_json` | `dict\|null` | Set for JSON/JSON_T9N features |
| `value_datetime` | `str\|null` | Set for DATETIME features |
| `attribute_idx` | `str\|null` | Set for SELECT features |
| `attribute_name` | `str\|null` | Resolved name for SELECT features |

**Status codes:** `200`, `401`, `403`, `404` (channel or product not found)

---

### Create Product

`POST {channel_idx}/products/`

**Request body `CreateProductRequest`:**

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `sku` | `str` | required | min 1, max 128 | Unique SKU. `get_or_create` RealProduct by SKU (shared across channels) |
| `feature_set_idx` | `str` | required | min 1 | Feature set identifier |
| `visibility` | `int` | `4` | ge=0, le=4 | 1=Not visible, 2=Catalog, 3=Search, 4=Catalog and search |
| `is_enabled` | `bool` | `true` | | Whether product is active |
| `product_class` | `int` | `1` | ge=0, le=4 | 0=Base, 1=Simple, 2=Configurable, 3=Bundle, 4=Custom |
| `kind_of_product` | `int` | `0` | ge=0, le=1 | 0=Physical, 1=Virtual |
| `ean` | `str\|null` | `null` | max 16 | EAN barcode |
| `weight` | `str\|null` | `null` | | Weight as decimal string |
| `width` | `str\|null` | `null` | | Width as decimal string |
| `height` | `str\|null` | `null` | | Height as decimal string |
| `deep` | `str\|null` | `null` | | Depth as decimal string |
| `attributes` | `list[ProductAttributeValueRequest]` | `[]` | | Attribute values to set on creation |
| `category_idxs` | `list[str]` | `[]` | | Category identifiers to assign |

**ProductAttributeValueRequest** (used in `attributes` list):

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `feature_idx` | `str` | required, min 1 | Feature to set value for |
| `value_bool` | `bool\|null` | optional | For BOOL features |
| `value_decimal` | `str\|null` | optional | For DECIMAL/TEMPERATURE/LENGTH/MASS features. Decimal as string |
| `value_txt` | `str\|null` | optional | For VARCHAR255/TEXT features |
| `value_txt_t9n` | `dict\|null` | optional | For T9N features. e.g. `{"en": "Red", "pl": "Czerwony"}` |
| `value_json` | `dict\|null` | optional | For JSON features |
| `value_datetime` | `str\|null` | optional | For DATETIME features. ISO 8601 string |
| `attribute_idx` | `str\|null` | optional | For SELECT features |
| `attribute_idxs` | `list[str]\|null` | optional | For MULTISELECT features |

**Response `201 ProductDetailResponse`** -- see Retrieve Product.

**Status codes:** `201`, `400`, `401`, `403`, `404` (channel or feature set not found)

---

### Update Product

`PATCH {channel_idx}/products/{sku}/`

All fields are optional. Omitted fields are unchanged.

**Request body `UpdateProductRequest`:**

| Field | Type | Notes |
|-------|------|-------|
| `ean` | `str\|null` | max 16 |
| `weight` | `str\|null` | **Shared across all channels using this SKU** |
| `width` | `str\|null` | **Shared across all channels** |
| `height` | `str\|null` | **Shared across all channels** |
| `deep` | `str\|null` | **Shared across all channels** |
| `feature_set_idx` | `str\|null` | |
| `visibility` | `int\|null` | |
| `is_enabled` | `bool\|null` | |
| `attributes` | `list[ProductAttributeValueRequest]\|null` | Per `feature_idx`: existing value replaced. Features not listed are untouched. |
| `category_idxs` | `list[str]\|null` | **Full replacement** of all category assignments when provided |

**Response `200 ProductDetailResponse`** -- see Retrieve Product.

**Status codes:** `200`, `400`, `401`, `403`, `404` (channel or product not found)

---

### Delete Product

`DELETE {channel_idx}/products/{sku}/`

Removes the channel `Product` record only. The `RealProduct` (shared SKU record with EAN and dimensions) is **not** deleted.

**Response `200`:**

```json
{"django_pim.Product": 1, "django_pim.ProductAttribute": 5, ...}
```

Cascade counts by Django model name.

**Status codes:** `200`, `401`, `403`, `404` (channel or product not found)

---

### Bulk Update Products

`POST {channel_idx}/products/bulk/`

**Request body `BulkProductUpdateRequest`:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `skus` | `list[str]` | min 1 item | SKUs to update |
| `is_enabled` | `bool\|null` | optional | Set enabled status on all listed products |
| `visibility` | `int\|null` | optional | Set visibility on all listed products |
| `category_idxs_add` | `list[str]\|null` | optional | Category identifiers to add (additive, not replacing) |
| `category_idxs_remove` | `list[str]\|null` | optional | Category identifiers to remove |

**Response `200`:**

```json
{"updated": 5}
```

**Status codes:** `200`, `400`, `401`, `403`, `404` (channel not found)

---

## Categories

All category endpoints are channel-scoped. Path parameter `{channel_idx}` is always required.

### Path Parameters

| Param | Type | Description |
|-------|------|-------------|
| `channel_idx` | `str` | Channel identifier (required on all category endpoints) |
| `idx` | `str` | Category slug identifier (required on retrieve, update, delete) |

### List Categories

`GET {channel_idx}/categories/`

**Query parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `search` | `str` | Filter by name (case-insensitive) |
| `is_active` | `bool` | Filter by active status. Accepts `true`/`1`/`yes` |
| `parent_category` | `int` | Filter by parent category PK |
| `root_only` | `bool` | Return only root categories (no parent). Accepts `true`/`1`/`yes` |
| `ordering` | `str` | Order by field. Examples: `name`, `-name`, `idx` |
| `page` | `int` | Page number |
| `page_size` | `int` | Items per page (max 100, default 20) |

**Response `200 CategoryListResponse`:**

| Field | Type | Description |
|-------|------|-------------|
| `count` | `int` | Total matching categories |
| `next` | `str\|null` | Next page URL |
| `previous` | `str\|null` | Previous page URL |
| `results` | `list[CategoryResponse]` | See CategoryResponse table |

**CategoryResponse** (used in list results):

| Field | Type | Description |
|-------|------|-------------|
| `pk` | `int` | Primary key |
| `idx` | `str` | Category slug identifier |
| `name` | `str` | Default language name |
| `parent_category` | `int\|null` | Parent category PK, null for root |
| `is_active` | `bool` | Whether category is active |

**Status codes:** `200`, `400`, `401`, `403`, `404` (channel not found)

---

### Retrieve Category

`GET {channel_idx}/categories/{idx}/`

**Response `200 CategoryDetailResponse`:**

| Field | Type | Description |
|-------|------|-------------|
| `pk` | `int` | Primary key |
| `idx` | `str` | Category identifier |
| `name` | `str` | Default language name |
| `name_t9n` | `dict` | Translated names |
| `description_t9n` | `dict` | Translated descriptions |
| `meta_title_t9n` | `dict` | Translated SEO titles |
| `meta_description_t9n` | `dict` | Translated SEO descriptions |
| `url_key_t9n` | `dict` | Auto-generated URL keys per language |
| `parent_category` | `int\|null` | Parent category PK |
| `parent_category_idx` | `str\|null` | Parent category idx |
| `breadcrumb_path` | `str` | e.g. `"Root > Electronics"` |
| `tree_deep` | `int` | Depth in category tree (0 = root) |
| `position` | `int\|null` | Sort position within siblings |
| `is_active` | `bool` | |
| `is_in_menu` | `bool` | Whether visible in navigation menu |
| `product_count` | `int` | Number of direct products in this category |
| `subcategory_count` | `int` | Number of direct subcategories |

**Status codes:** `200`, `401`, `403`, `404` (channel or category not found)

---

### Create Category

`POST {channel_idx}/categories/`

**Request body `CreateCategoryRequest`:**

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `idx` | `str` | required | min 1, max 128 | Slug, unique within channel |
| `name_t9n` | `dict` | required | | e.g. `{"en": "Electronics", "pl": "Elektronika"}` |
| `description_t9n` | `dict` | `{}` | | Translated descriptions |
| `meta_title_t9n` | `dict` | `{}` | | Translated SEO titles |
| `meta_description_t9n` | `dict` | `{}` | | Translated SEO descriptions |
| `parent_category_idx` | `str\|null` | `null` | | Parent category idx. Null for root categories |
| `position` | `int\|null` | `null` | | Sort order within siblings |
| `is_active` | `bool` | `true` | | |
| `is_in_menu` | `bool` | `true` | | Whether visible in navigation menu |

**Response `201 CategoryDetailResponse`** -- see Retrieve Category.

**Status codes:** `201`, `400`, `401`, `403`, `404` (channel or parent category not found)

---

### Update Category

`PATCH {channel_idx}/categories/{idx}/`

All fields are optional. Omitted fields are unchanged. Setting `parent_category_idx=null` promotes the category to root (removes parent).

**Request body `UpdateCategoryRequest`:**

| Field | Type | Notes |
|-------|------|-------|
| `name_t9n` | `dict\|null` | Full replacement when provided |
| `description_t9n` | `dict\|null` | Full replacement when provided |
| `meta_title_t9n` | `dict\|null` | Full replacement when provided |
| `meta_description_t9n` | `dict\|null` | Full replacement when provided |
| `parent_category_idx` | `str\|null` | Null = make root. Validates against circular references |
| `position` | `int\|null` | |
| `is_active` | `bool\|null` | |
| `is_in_menu` | `bool\|null` | |

**Response `200 CategoryDetailResponse`** -- see Retrieve Category.

**Status codes:** `200`, `400` (validation error or circular reference), `401`, `403`, `404`

---

### Delete Category

`DELETE {channel_idx}/categories/{idx}/`

CASCADE deletes subcategories and all `ProductInCategory` assignments.

**Response `200`:**

```json
{"django_pim.ProductCategory": 3, "django_pim.ProductInCategory": 12, ...}
```

**Status codes:** `200`, `401`, `403`, `404`

---

## Features

Features can be accessed globally (for writes) or scoped to a channel (read-only). Features are not channel-owned -- they are global with scope levels.

### Path Parameters

| Param | Type | Description |
|-------|------|-------------|
| `idx` | `str` | Feature slug identifier |
| `channel_idx` | `str` | Channel identifier (optional, for channel-scoped read routes) |

### List Features

`GET features/` or `GET {channel_idx}/features/`

**Query parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `search` | `str` | Filter by idx (case-insensitive) |
| `scope` | `int` | Filter by scope: 1=SYSTEM, 2=GLOBAL, 3=BUSINESS_UNIT |
| `feature_type` | `int` | Filter by feature type enum value |
| `is_filterable` | `bool` | Filter by filterable status |
| `is_searchable` | `bool` | Filter by searchable status |
| `is_visible` | `bool` | Filter by visible status |
| `include_system` | `bool` | Include SYSTEM scope features (only meaningful with channel context) |
| `ordering` | `str` | Order by field. Examples: `display_order`, `-idx` |
| `page` | `int` | Page number |
| `page_size` | `int` | Items per page (max 100, default 20) |

**Response `200 FeatureListResponse`:**

| Field | Type | Description |
|-------|------|-------------|
| `count` | `int` | Total matching features |
| `next` | `str\|null` | Next page URL |
| `previous` | `str\|null` | Previous page URL |
| `results` | `list[FeatureResponse]` | See FeatureResponse table |

**Status codes:** `200`, `400`, `401`, `403`, `404`

---

### Retrieve Feature

`GET features/{idx}/` or `GET {channel_idx}/features/{idx}/`

**Response `200 FeatureResponse`:**

| Field | Type | Description |
|-------|------|-------------|
| `pk` | `int` | Primary key |
| `idx` | `str` | Unique slug identifier |
| `name` | `str` | Resolved display name |
| `scope` | `int` | Scope enum value |
| `scope_name` | `str` | Scope label |
| `feature_type` | `int` | Feature type enum value |
| `feature_type_name` | `str` | Feature type label |
| `frontend_input_type` | `int` | Frontend input type enum value |
| `frontend_input_type_name` | `str` | Frontend input type label |
| `filter_type` | `int` | Filter type enum value |
| `filter_type_name` | `str` | Filter type label |
| `display_order` | `int` | Sort order (lower = first) |
| `is_required` | `bool` | Whether required on every product |
| `is_visible` | `bool` | Whether visible on product detail pages |
| `is_filterable` | `bool` | Whether available as storefront filter facet |
| `is_searchable` | `bool` | Whether indexed for full-text search |
| `is_comparable` | `bool` | Whether shown in product comparison tables |
| `is_for_customization` | `bool` | Whether drives product customization options |

**Status codes:** `200`, `401`, `403`, `404`

---

### Create Feature

`POST features/`

**Request body `CreateFeatureRequest`:**

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `idx` | `str` | required | min 1, max 128 | Unique slug. Permanent key across translations |
| `name_t9n` | `dict` | required | | e.g. `{"en": "Color", "pl": "Kolor"}` |
| `scope` | `int` | `3` | ge=1, le=3 | 1=SYSTEM, 2=GLOBAL, 3=BUSINESS_UNIT |
| `feature_type` | `int` | `0` | ge=0, le=14 | See Feature Types reference table |
| `frontend_input_type` | `int` | `0` | ge=0, le=8 | See Frontend Input Types table |
| `filter_type` | `int` | `0` | ge=0, le=5 | See Filter Types table |
| `display_order` | `int\|null` | `null` | ge=0 | Lower = first. Auto-assigned when null |
| `is_required` | `bool` | `false` | | Required on every product |
| `is_visible` | `bool` | `true` | | Visible on product detail pages |
| `is_filterable` | `bool` | `false` | | Available as storefront filter facet |
| `is_searchable` | `bool` | `true` | | Indexed for full-text search |
| `is_comparable` | `bool` | `false` | | Shown in product comparison tables |
| `is_for_customization` | `bool` | `false` | | Drives product customization options |

**Response `201 FeatureResponse`** -- see Retrieve Feature.

**Status codes:** `201`, `400`, `401`, `403`

---

### Update Feature

`PATCH features/{idx}/`

All fields are optional. Same types and constraints as `CreateFeatureRequest`.

**Request body `UpdateFeatureRequest`:**

| Field | Type | Notes |
|-------|------|-------|
| `name_t9n` | `dict\|null` | Replaces entire translation map when provided |
| `scope` | `int\|null` | ge=1, le=3 |
| `feature_type` | `int\|null` | ge=0, le=14 |
| `frontend_input_type` | `int\|null` | ge=0, le=8 |
| `filter_type` | `int\|null` | ge=0, le=5 |
| `display_order` | `int\|null` | ge=0 |
| `is_required` | `bool\|null` | |
| `is_visible` | `bool\|null` | |
| `is_filterable` | `bool\|null` | |
| `is_searchable` | `bool\|null` | |
| `is_comparable` | `bool\|null` | |
| `is_for_customization` | `bool\|null` | |

**Response `200 FeatureResponse`** -- see Retrieve Feature.

**Status codes:** `200`, `400`, `401`, `403`, `404`

---

### Delete Feature

`DELETE features/{idx}/`

**Response `200`:**

```json
{"deleted": {"django_pim.Feature": 1, "django_pim.FeatureInFeatureSet": 2, ...}}
```

Cascade counts by Django model name.

**Status codes:** `200`, `401`, `403`, `404`

---

### List Attributes for Feature

`GET features/{idx}/attributes/` or `GET {channel_idx}/features/{idx}/attributes/`

Returns paginated `AttributeListResponse` (see Attributes section).

**Query parameters:** `page`, `page_size` only.

**Status codes:** `200`, `401`, `403`, `404`

---

## Feature Types Reference

| Value | Name | Storage field in ProductAttributeValueRequest/Response |
|-------|------|-------------------------------------------------------|
| 0 | UNKNOWN | -- |
| 1 | BOOL | `value_bool` |
| 2 | DECIMAL | `value_decimal` |
| 3 | VARCHAR255 | `value_txt` |
| 4 | VARCHAR255_T9N | `value_txt_t9n` |
| 5 | TEXT | `value_txt` |
| 6 | TEXT_T9N | `value_txt_t9n` |
| 7 | SELECT | `attribute_idx` |
| 8 | MULTISELECT | `attribute_idxs` |
| 9 | JSON | `value_json` |
| 10 | DATETIME | `value_datetime` |
| 11 | JSON_T9N | `value_json` |
| 12 | TEMPERATURE | `value_decimal` |
| 13 | LENGTH | `value_decimal` |
| 14 | MASS | `value_decimal` |

## Frontend Input Types Reference

| Value | Name |
|-------|------|
| 0 | DEFAULT |
| 1 | SELECT_SWATCH_VISUAL |
| 2 | SELECT_SWATCH_TEXT |
| 3 | DROPDOWN |
| 4 | DROPDOWN_WITH_PRICE |
| 5 | PALETTE_COLOR |
| 6 | SLIDER |
| 7 | BOOLEAN |
| 8 | RADIO |

## Filter Types Reference

| Value | Name |
|-------|------|
| 0 | DEFAULT |
| 1 | SELECT_SWATCH_IMAGE |
| 2 | SELECT_SWATCH_TEXT |
| 3 | SLIDE |
| 4 | BOOLEAN |
| 5 | RADIO_TEXT |

---

## Feature Sets

Feature sets are global resources (not channel-owned). Write operations (create/update/delete) use global routes. Read operations (list/retrieve) are available on both global and channel-scoped routes.

### Path Parameters

| Param | Type | Description |
|-------|------|-------------|
| `idx` | `str` | Feature set slug identifier |
| `channel_idx` | `str` | Channel identifier (optional, for channel-scoped read routes) |

### List Feature Sets

`GET feature-sets/` or `GET {channel_idx}/feature-sets/`

**Query parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `search` | `str` | Filter by idx or name |
| `is_default` | `bool` | Filter by default status |
| `ordering` | `str` | Order by field. Examples: `idx`, `-name` |
| `page` | `int` | Page number |
| `page_size` | `int` | Items per page (max 100, default 20) |

**Response `200 FeatureSetListResponse`:**

| Field | Type | Description |
|-------|------|-------------|
| `count` | `int` | Total matching feature sets |
| `next` | `str\|null` | Next page URL |
| `previous` | `str\|null` | Previous page URL |
| `results` | `list[FeatureSetResponse]` | See FeatureSetResponse table |

**Status codes:** `200`, `400`, `401`, `403`, `404`

---

### Retrieve Feature Set

`GET feature-sets/{idx}/` or `GET {channel_idx}/feature-sets/{idx}/`

**Response `200 FeatureSetResponse`:**

| Field | Type | Description |
|-------|------|-------------|
| `pk` | `int` | Primary key |
| `idx` | `str` | Unique slug identifier |
| `name` | `str` | Display name |
| `desc` | `str` | Internal description |
| `is_default` | `bool` | Whether this is the default feature set for new products |
| `feature_count` | `int` | Number of features in this set |

**Status codes:** `200`, `401`, `403`, `404`

---

### Create Feature Set

`POST feature-sets/`

**Request body `CreateFeatureSetRequest`:**

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `idx` | `str` | required | min 1, max 256 | Unique slug |
| `name` | `str` | `""` | max 256 | Display name |
| `desc` | `str` | `""` | | Internal description |
| `is_default` | `bool` | `false` | | Applied to new products without explicit feature set assignment |

**Response `201 FeatureSetResponse`** -- see Retrieve Feature Set.

**Status codes:** `201`, `400`, `401`, `403`

---

### Update Feature Set

`PATCH feature-sets/{idx}/`

**Request body `UpdateFeatureSetRequest`:**

| Field | Type | Notes |
|-------|------|-------|
| `name` | `str\|null` | max 256 |
| `desc` | `str\|null` | |
| `is_default` | `bool\|null` | |

**Response `200 FeatureSetResponse`** -- see Retrieve Feature Set.

**Status codes:** `200`, `400`, `401`, `403`, `404`

---

### Delete Feature Set

`DELETE feature-sets/{idx}/`

**Response `200`:**

```json
{"deleted": {"django_pim.FeatureSet": 1, ...}}
```

**Status codes:** `200`, `401`, `403`, `404`

---

### List Features in Feature Set

`GET feature-sets/{idx}/features/` or `GET {channel_idx}/feature-sets/{idx}/features/`

Returns features within the set, ordered by position.

**Query parameters:** `page`, `page_size` only.

**Response `200 FeaturesInSetListResponse`:**

| Field | Type | Description |
|-------|------|-------------|
| `count` | `int` | Total features in set |
| `next` | `str\|null` | Next page URL |
| `previous` | `str\|null` | Previous page URL |
| `results` | `list[FeatureInSetResponse]` | See FeatureInSetResponse table |

**FeatureInSetResponse:**

| Field | Type | Description |
|-------|------|-------------|
| `position` | `int` | Sort position within the set (lower = first) |
| `feature` | `FeatureResponse` | Full feature details (see Retrieve Feature) |

**Status codes:** `200`, `401`, `403`, `404`

---

### Add Features to Feature Set

`POST feature-sets/{idx}/features/`

Idempotent -- features already present in the set are ignored.

**Request body `BulkAddFeaturesRequest`:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `features` | `list[FeatureInSetEntry]` | min 1 item | Features to add |

**FeatureInSetEntry:**

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `feature_idx` | `str` | required | min 1, max 128 | Feature identifier |
| `position` | `int\|null` | `null` | ge=0 | Position in set. Auto-assigned starting at 500 when null |

**Response `201`:** Array of `FeatureInSetResponse` entries for features that were added.

**Status codes:** `201`, `400`, `401`, `403`, `404` (feature set or feature not found)

---

### Remove Features from Feature Set

`DELETE feature-sets/{idx}/features/`

Idempotent -- features not present in the set are ignored.

**Request body `BulkRemoveFeaturesRequest`:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `feature_idxs` | `list[str]` | min 1 item | Feature identifiers to remove |

**Response `200`:**

```json
{"removed": 3}
```

**Status codes:** `200`, `400`, `401`, `403`, `404` (feature set not found)

---

## Attributes

Attributes belong to a feature and use a **composite key** (`feature_idx` + `idx`). There are no channel-scoped attribute routes -- all attribute operations are global.

### Path Parameters

| Param | Type | Description |
|-------|------|-------------|
| `feature_idx` | `str` | Parent feature identifier (part of composite key) |
| `idx` | `str` | Attribute identifier within its feature (part of composite key) |

### List Attributes

`GET attributes/`

**Query parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `feature_idx` | `str` | Filter by parent feature identifier |
| `group_idx` | `str` | Filter by attributes group identifier |
| `search` | `str` | Search by idx or name |
| `page` | `int` | Page number |
| `page_size` | `int` | Items per page (max 100, default 20) |

**Response `200 AttributeListResponse`:**

| Field | Type | Description |
|-------|------|-------------|
| `count` | `int` | Total matching attributes |
| `next` | `str\|null` | Next page URL |
| `previous` | `str\|null` | Previous page URL |
| `results` | `list[AttributeResponse]` | See AttributeResponse table |

**Status codes:** `200`, `400`, `401`, `403`

---

### Retrieve Attribute

`GET attributes/{feature_idx}/{idx}/`

**Response `200 AttributeResponse`:**

| Field | Type | Description |
|-------|------|-------------|
| `pk` | `int` | Primary key |
| `feature_idx` | `str` | Parent feature identifier (part of composite key) |
| `idx` | `str` | Attribute identifier within feature (part of composite key) |
| `name` | `str` | Resolved display name |
| `group_idx` | `str\|null` | Attributes group identifier, null if no group |
| `display_order` | `int` | Sort order within feature (lower = first) |

**Status codes:** `200`, `401`, `403`, `404`

---

### Create Attribute

`POST attributes/`

**Request body `CreateAttributeRequest`:**

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `feature_idx` | `str` | required | min 1, max 128 | Parent feature identifier |
| `idx` | `str` | required | min 1, max 128 | Unique within this feature. Forms composite key with `feature_idx` |
| `name_t9n` | `dict` | required | | e.g. `{"en": "Red", "pl": "Czerwony"}` |
| `group_idx` | `str\|null` | `null` | | Attributes group to assign to |
| `display_order` | `int` | `100` | ge=0 | Sort order within feature |

**Response `201 AttributeResponse`** -- see Retrieve Attribute.

**Status codes:** `201`, `400` (validation error or duplicate), `401`, `403`, `404` (feature or group not found)

---

### Update Attribute

`PATCH attributes/{feature_idx}/{idx}/`

**Request body `UpdateAttributeRequest`:**

| Field | Type | Notes |
|-------|------|-------|
| `name_t9n` | `dict\|null` | Replaces entire translation map when provided |
| `group_idx` | `str\|null` | Null removes group assignment |
| `display_order` | `int\|null` | ge=0 |

**Response `200 AttributeResponse`** -- see Retrieve Attribute.

**Status codes:** `200`, `400`, `401`, `403`, `404`

---

### Delete Attribute

`DELETE attributes/{feature_idx}/{idx}/`

**Response `200`:**

```json
{"deleted": {"django_pim.Attribute": 1, ...}}
```

**Status codes:** `200`, `401`, `403`, `404`

---

## Attributes Groups

Attributes groups cluster related attributes (e.g. `"warm-colors"` clusters `red`, `orange`, `yellow`). Attributes reference a group via their `group_idx` field.

Write operations (create/update/delete) use global routes. Read operations are available on both global and channel-scoped routes.

### Path Parameters

| Param | Type | Description |
|-------|------|-------------|
| `idx` | `str` | Attributes group slug identifier |
| `channel_idx` | `str` | Channel identifier (optional, for channel-scoped read routes) |

### List Attributes Groups

`GET attributes-groups/` or `GET {channel_idx}/attributes-groups/`

**Query parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `search` | `str` | Filter by idx or name |
| `ordering` | `str` | Order by field. Examples: `idx`, `-idx` |
| `page` | `int` | Page number |
| `page_size` | `int` | Items per page (max 100, default 20) |

**Response `200 AttributesGroupListResponse`:**

| Field | Type | Description |
|-------|------|-------------|
| `count` | `int` | Total matching groups |
| `next` | `str\|null` | Next page URL |
| `previous` | `str\|null` | Previous page URL |
| `results` | `list[AttributesGroupResponse]` | See AttributesGroupResponse table |

**Status codes:** `200`, `400`, `401`, `403`, `500`

---

### Retrieve Attributes Group

`GET attributes-groups/{idx}/` or `GET {channel_idx}/attributes-groups/{idx}/`

**Response `200 AttributesGroupResponse`:**

| Field | Type | Description |
|-------|------|-------------|
| `pk` | `int` | Primary key |
| `idx` | `str` | Unique slug identifier |
| `name` | `str` | Resolved display name |
| `attribute_count` | `int` | Number of attributes assigned to this group |

**Status codes:** `200`, `401`, `403`, `404`

---

### Create Attributes Group

`POST attributes-groups/`

**Request body `CreateAttributesGroupRequest`:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `idx` | `str` | required, min 1, max 128 | Unique slug. Referenced by attributes via their `group_idx` field |
| `name_t9n` | `dict` | required | e.g. `{"en": "Warm Colors", "pl": "Ciepłe Kolory"}` |

**Response `201 AttributesGroupResponse`** -- see Retrieve Attributes Group.

**Status codes:** `201`, `400` (validation error or duplicate idx), `401`, `403`

---

### Update Attributes Group

`PATCH attributes-groups/{idx}/`

**Request body `UpdateAttributesGroupRequest`:**

| Field | Type | Notes |
|-------|------|-------|
| `name_t9n` | `dict\|null` | Replaces entire translation map when provided |

**Response `200 AttributesGroupResponse`** -- see Retrieve Attributes Group.

**Status codes:** `200`, `400`, `401`, `403`, `404`

---

### Delete Attributes Group

`DELETE attributes-groups/{idx}/`

**Response `200`:**

```json
{"deleted": {"django_pim.AttributesGroup": 1, ...}}
```

**Status codes:** `200`, `401`, `403`, `404`

---

## OpenAPI Tags

| Tag | ViewSet |
|-----|---------|
| `Products` | `ProductViewSet` -- all actions |
| `Categories` | `CategoryViewSet` -- all actions |
| `Features` | `FeatureViewSet` -- all actions |
| `Feature Sets` | `FeatureSetViewSet` -- all actions |
| `Attributes` | `AttributeViewSet` -- all actions |
| `Attributes Groups` | `AttributesGroupViewSet` -- all actions |

Browsable API reference rendered by starlight-openapi at `/api/reference/`. Swagger UI: `http://localhost:8000/api/docs/`.

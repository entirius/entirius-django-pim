# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Product response schemas for django-pim APIs."""

from pydantic import BaseModel, ConfigDict, Field


class ProductResponse(BaseModel):
    """
    Response schema for a single product.

    Contains essential product information for API responses.
    """

    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(..., description="Product primary key", examples=[1, 42, 123])
    sku: str = Field(
        ...,
        description="Stock Keeping Unit - unique product identifier",
        examples=["PROD-001", "SKU-12345"],
        min_length=1,
        max_length=255,
    )
    name: str = Field(
        ..., description="Product name", examples=["Laptop Pro 15", "Wireless Mouse"], min_length=1, max_length=500
    )
    visibility: str = Field(
        ...,
        description="Product visibility setting",
        examples=["Catalog and search", "Catalog", "Search", "Not visible individually"],
    )
    visibility_int: int = Field(
        ..., description="Product visibility as integer for filter round-tripping", examples=[1, 2, 3, 4]
    )
    is_enabled: bool = Field(..., description="Whether the product is enabled and available", examples=[True, False])
    product_class: int = Field(
        ..., description="Product class enum value (1=Simple, 2=Configurable, 3=Bundle)", examples=[1, 2, 3]
    )
    product_class_name: str = Field(
        ...,
        description="Product class display label",
        examples=["ProductSimple", "ProductConfigurable", "ProductBundle"],
    )
    feature_set_idx: str = Field(
        ..., description="Feature set identifier used by this product", examples=["default", "furniture"]
    )
    thumbnail_url: str | None = Field(
        None,
        description="URL of the main product picture (null if no main picture)",
        examples=["/media/image/abc123.png", None],
    )
    gap_worst_severity: str | None = Field(
        None,
        description="Worst quality-gap severity: critical | warning | null (no gaps / not evaluated)",
        examples=["critical", "warning", None],
    )
    gap_count: int = Field(0, ge=0, description="Number of open quality gaps", examples=[0, 3])
    gap_evaluated_at: str | None = Field(
        None,
        description="ISO8601 of last gap evaluation; null = never evaluated / unevaluable (ProductCustom)",
        examples=["2026-06-07T10:00:00+00:00", None],
    )


class ProductListResponse(BaseModel):
    """
    Response schema for paginated product list.

    Contains pagination metadata and list of products.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Total number of products matching the query", examples=[0, 10, 150], ge=0)
    next: str | None = Field(
        None,
        description="URL to next page of results (null if no next page)",
        examples=["/api/pim/admin/shop/products/?page=2", None],
    )
    previous: str | None = Field(
        None,
        description="URL to previous page of results (null if no previous page)",
        examples=["/api/pim/admin/shop/products/?page=1", None],
    )
    results: list[ProductResponse] = Field(..., description="List of products in the current page", examples=[[]])


class ProductAttributeValueResponse(BaseModel):
    """Response schema for a single product attribute value."""

    model_config = ConfigDict(from_attributes=True)

    feature_idx: str = Field(description="Feature identifier", examples=["color"])
    feature_name: str = Field(description="Feature display name", examples=["Color"])
    feature_type: int = Field(description="Feature type enum value", examples=[7])
    feature_type_name: str = Field(description="Feature type label", examples=["Select"])
    value_bool: bool | None = Field(None, description="Boolean value", examples=[True])
    value_decimal: str | None = Field(None, description="Decimal value as string", examples=["19.99"])
    value_txt: str | None = Field(None, description="Plain text value", examples=["Red"])
    value_txt_t9n: dict | None = Field(
        None, description="Translated text value", examples=[{"en": "Red", "pl": "Czerwony"}]
    )
    value_json: dict | None = Field(None, description="JSON value", examples=[None])
    value_datetime: str | None = Field(None, description="Datetime value", examples=["2024-01-01T00:00:00"])
    attribute_idx: str | None = Field(None, description="Attribute identifier (for SELECT types)", examples=["red"])
    attribute_name: str | None = Field(None, description="Attribute display name", examples=["Red"])
    overridden_langs: list[str] = Field(
        default_factory=list, description="Languages explicitly overridden (not inherited)", examples=[["en"]]
    )
    inherited_values: dict | None = Field(
        None,
        description="Values from default channel (for comparison in CMS UI)",
        examples=[{"en": "Chair", "pl": "Krzesło"}],
    )


class ProductCategoryBriefResponse(BaseModel):
    """Brief category info for product detail response."""

    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(description="Category primary key", examples=[1])
    idx: str = Field(description="Category identifier", examples=["electronics"])
    name: str = Field(description="Category display name", examples=["Electronics"])
    breadcrumb_path: str = Field(description="Full breadcrumb path", examples=["Root > Electronics"])


class ProductDetailResponse(BaseModel):
    """Full product detail response with attributes and categories."""

    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(description="Product primary key", examples=[1])
    sku: str = Field(description="Stock Keeping Unit", examples=["PROD-001"])
    name: str = Field(description="Product name", examples=["Laptop Pro 15"])
    name_t9n: dict = Field(
        description="Translated product names", examples=[{"en": "Laptop Pro 15", "pl": "Laptop Pro 15"}]
    )
    description_t9n: dict = Field(description="Translated descriptions", examples=[{"en": "A great laptop"}])
    short_description_t9n: dict = Field(
        default_factory=dict, description="Translated short descriptions", examples=[{"en": "Great laptop for work"}]
    )
    url_key_t9n: dict = Field(
        default_factory=dict, description="Translated URL keys (SEO slugs)", examples=[{"en": "laptop-pro-15"}]
    )
    meta_title_t9n: dict = Field(
        default_factory=dict, description="Translated SEO meta titles", examples=[{"en": "Buy Laptop Pro 15 | Shop"}]
    )
    meta_description_t9n: dict = Field(
        default_factory=dict,
        description="Translated SEO meta descriptions",
        examples=[{"en": "Premium ergonomic chair with lumbar support."}],
    )
    canonical_url_t9n: dict = Field(
        default_factory=dict,
        description="Translated canonical URLs for SEO",
        examples=[{"en": "https://example.com/laptop-pro-15"}],
    )
    og_image: str = Field(
        "", description="Open Graph image URL for social sharing", examples=["https://example.com/og.jpg"]
    )
    subname_t9n: dict = Field(
        default_factory=dict, description="Translated product subtitle", examples=[{"en": "Professional Edition"}]
    )
    subname2_t9n: dict = Field(
        default_factory=dict, description="Translated product subtitle 2", examples=[{"en": "Limited Collection"}]
    )
    visibility: int = Field(description="Visibility enum value", examples=[4])
    visibility_name: str = Field(description="Visibility label", examples=["Catalog and search"])
    is_enabled: bool = Field(description="Whether product is enabled", examples=[True])
    product_class: int = Field(description="Product class enum value", examples=[1])
    product_class_name: str = Field(description="Product class label", examples=["ProductSimple"])
    feature_set_idx: str = Field(description="Feature set identifier", examples=["default"])
    weight: str | None = Field(None, description="Product weight", examples=["1.50"])
    width: str | None = Field(None, description="Product width", examples=["30.00"])
    height: str | None = Field(None, description="Product height", examples=["20.00"])
    deep: str | None = Field(None, description="Product depth", examples=["5.00"])
    ean: str | None = Field(None, description="EAN barcode", examples=["5901234123457"])
    kind_of_product: int = Field(description="Kind of product enum", examples=[0])
    inherit_attributes: bool = Field(
        default=False,
        description="Whether this product inherits technical attributes from default channel",
        examples=[False],
    )
    inherit_descriptions: bool = Field(
        default=False,
        description="Whether this product inherits name/description/short_description from default channel",
        examples=[False],
    )
    inherit_images: bool = Field(
        default=False,
        description="Whether this product inherits pictures/videos/files from default channel",
        examples=[False],
    )
    default_channel_idx: str | None = Field(
        None,
        description="Default channel identifier (only present when inheritance is active)",
        examples=["default-local"],
    )
    present_in_channels: list[str] = Field(
        default_factory=list,
        description="Channel idxs where this SKU exists (via RealProduct)",
        examples=[["default-europe", "poland-local"]],
    )
    inheriting_channels_count: int = Field(
        default=0, description="Number of non-default channels inheriting from this product", examples=[0, 3]
    )
    categories: list[ProductCategoryBriefResponse] = Field(default_factory=list, description="Product categories")
    attributes: list[ProductAttributeValueResponse] = Field(
        default_factory=list, description="Product attribute values"
    )
    gap_worst_severity: str | None = Field(
        None,
        description="Worst quality-gap severity: critical | warning | null (no gaps / not evaluated)",
        examples=["critical", "warning", None],
    )
    gap_count: int = Field(0, ge=0, description="Number of open quality gaps", examples=[0, 3])
    gap_evaluated_at: str | None = Field(
        None,
        description="ISO8601 of last gap evaluation; null = never evaluated / unevaluable (ProductCustom)",
        examples=["2026-06-07T10:00:00+00:00", None],
    )

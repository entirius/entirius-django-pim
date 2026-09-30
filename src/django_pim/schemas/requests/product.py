# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Product request schemas for django-pim Admin API v2."""

from pydantic import BaseModel, Field, field_validator

from django_pim.validators import validate_routable_sku


class ProductAttributeValueRequest(BaseModel):
    """Request schema for a single product attribute value."""

    feature_idx: str = Field(description="Feature identifier to set value for", examples=["color"], min_length=1)
    value_bool: bool | None = Field(None, description="Boolean value (for BOOL features)", examples=[True])
    value_decimal: str | None = Field(
        None, description="Decimal value as string (for DECIMAL features)", examples=["19.99"]
    )
    value_txt: str | None = Field(None, description="Plain text value (for VARCHAR255/TEXT features)", examples=["Red"])
    value_txt_t9n: dict | None = Field(
        None, description="Translated text value (for T9N features)", examples=[{"en": "Red", "pl": "Czerwony"}]
    )
    value_json: dict | None = Field(None, description="JSON value (for JSON features)")
    value_datetime: str | None = Field(
        None, description="Datetime value (for DATETIME features)", examples=["2024-01-01T00:00:00"]
    )
    attribute_idx: str | None = Field(None, description="Attribute identifier (for SELECT features)", examples=["red"])
    attribute_idxs: list[str] | None = Field(
        None, description="Attribute identifiers (for MULTISELECT features)", examples=[["red", "blue"]]
    )


class CreateProductRequest(BaseModel):
    """Request schema for creating a new product."""

    sku: str = Field(
        description="Stock Keeping Unit - must be unique within the channel",
        examples=["PROD-001"],
        min_length=1,
        max_length=128,
    )
    ean: str | None = Field(None, description="EAN barcode", examples=["5901234123457"], max_length=16)
    kind_of_product: int = Field(0, description="Kind of product: 0=Physical, 1=Virtual", examples=[0], ge=0, le=1)

    @field_validator("sku")
    @classmethod
    def _sku_not_route_reserved(cls, value: str) -> str:
        validate_routable_sku(value)
        return value

    weight: str | None = Field(
        None,
        description="Product weight (unit: DEFAULT_MASS_UNIT, grams by default; stored as given, no conversion)",
        examples=["1500.00"],
    )
    width: str | None = Field(
        None,
        description="Product width (unit: DEFAULT_LENGTH_UNIT, millimetres by default; stored as given, no conversion)",
        examples=["300.00"],
    )
    height: str | None = Field(
        None,
        description="Product height (unit: DEFAULT_LENGTH_UNIT, millimetres by default; stored as given, no conversion)",
        examples=["200.00"],
    )
    deep: str | None = Field(
        None,
        description="Product depth (unit: DEFAULT_LENGTH_UNIT, millimetres by default; stored as given, no conversion)",
        examples=["50.00"],
    )
    feature_set_idx: str = Field(
        description="Feature set identifier for the product", examples=["default"], min_length=1
    )
    visibility: int = Field(
        4,
        description=("Visibility: 1=Not visible, 2=Catalog, 3=Search, 4=Catalog and search"),
        examples=[4],
        ge=0,
        le=4,
    )
    is_enabled: bool = Field(True, description="Whether the product is enabled", examples=[True])
    product_class: int = Field(
        1, description=("Product class: 0=Base, 1=Simple, 2=Configurable, 3=Bundle, 4=Custom"), examples=[1], ge=0, le=4
    )
    attributes: list[ProductAttributeValueRequest] = Field(
        default_factory=list, description="Product attribute values to set"
    )
    category_idxs: list[str] = Field(
        default_factory=list,
        description="Category identifiers to assign product to",
        examples=[["electronics", "laptops"]],
    )


class UpdateProductRequest(BaseModel):
    """Request schema for updating a product (PATCH - all fields optional)."""

    ean: str | None = Field(None, description="EAN barcode", examples=["5901234123457"], max_length=16)
    weight: str | None = Field(
        None,
        description="Product weight (shared across channels) (unit: DEFAULT_MASS_UNIT, grams by default; stored as given, no conversion)",
        examples=["1500.00"],
    )
    width: str | None = Field(
        None,
        description="Product width (shared across channels) (unit: DEFAULT_LENGTH_UNIT, millimetres by default; stored as given, no conversion)",
        examples=["300.00"],
    )
    height: str | None = Field(
        None,
        description="Product height (shared across channels) (unit: DEFAULT_LENGTH_UNIT, millimetres by default; stored as given, no conversion)",
        examples=["200.00"],
    )
    deep: str | None = Field(
        None,
        description="Product depth (shared across channels) (unit: DEFAULT_LENGTH_UNIT, millimetres by default; stored as given, no conversion)",
        examples=["50.00"],
    )
    feature_set_idx: str | None = Field(None, description="Feature set identifier", examples=["default"])
    visibility: int | None = Field(
        None, description=("Visibility: 1=Not visible, 2=Catalog, 3=Search, 4=Catalog and search"), examples=[4]
    )
    is_enabled: bool | None = Field(None, description="Whether the product is enabled", examples=[True])
    attributes: list[ProductAttributeValueRequest] | None = Field(
        None,
        description=(
            "Product attribute values. For each feature_idx in the list, existing values "
            "are replaced. Features not listed are untouched."
        ),
    )
    category_idxs: list[str] | None = Field(
        None,
        description=("Category identifiers. Fully replaces all category assignments when provided."),
        examples=[["electronics", "laptops"]],
    )
    inherit_attributes: bool | None = Field(
        None, description="Toggle attribute inheritance from the default channel.", examples=[True]
    )
    inherit_descriptions: bool | None = Field(
        None, description="Toggle description (name/description/short_description) inheritance.", examples=[True]
    )
    inherit_images: bool | None = Field(
        None, description="Toggle media (pictures/videos/files) inheritance.", examples=[True]
    )


class BulkProductUpdateRequest(BaseModel):
    """Request schema for bulk updating multiple products."""

    skus: list[str] = Field(
        description="List of product SKUs to update", examples=[["PROD-001", "PROD-002"]], min_length=1
    )
    is_enabled: bool | None = Field(None, description="Set enabled status for all listed products", examples=[True])
    visibility: int | None = Field(None, description="Set visibility for all listed products", examples=[4])
    category_idxs_add: list[str] | None = Field(
        None, description="Category identifiers to add to all listed products", examples=[["new-category"]]
    )
    category_idxs_remove: list[str] | None = Field(
        None, description="Category identifiers to remove from all listed products", examples=[["old-category"]]
    )

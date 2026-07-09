# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Response schemas for product position in category."""

from pydantic import BaseModel, ConfigDict, Field


class ProductInCategoryResponse(BaseModel):
    """A product within a category with its position."""

    model_config = ConfigDict(from_attributes=True)

    sku: str = Field(description="Product SKU identifier", examples=["CHAIR-001"])
    name: str = Field(description="Product display name", examples=["Ergonomic Office Chair"])
    position: int = Field(description="Position in category (0=unpositioned, >0=pinned)", examples=[1])
    is_enabled: bool = Field(description="Whether the product is enabled", examples=[True])
    thumbnail_url: str | None = Field(
        default=None, description="Product thumbnail URL", examples=["https://cdn.example.com/thumb.jpg"]
    )


class ProductInCategoryListResponse(BaseModel):
    """Response for listing products in a category with positioned/unpositioned split."""

    positioned: list[ProductInCategoryResponse] = Field(description="Products with position > 0, ordered by position")
    unpositioned_count: int = Field(description="Total count of unpositioned products", examples=[128])
    unpositioned: list[ProductInCategoryResponse] = Field(description="Paginated unpositioned products (position = 0)")
    unpositioned_next: int | None = Field(
        default=None, description="Next page number for unpositioned products, or null", examples=[2]
    )
    unpositioned_previous: int | None = Field(
        default=None, description="Previous page number for unpositioned products, or null", examples=[1]
    )

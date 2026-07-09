# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Response schemas for product links."""

from pydantic import BaseModel, ConfigDict, Field


class LinkedProductBriefResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(description="Product primary key", examples=[42])
    sku: str = Field(description="Product SKU", examples=["CHAIR-001"])
    name: str = Field(description="Product display name", examples=["Ergonomic Chair"])


class ProductLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(description="ProductLink primary key", examples=[1])
    linked_product: LinkedProductBriefResponse = Field(description="Brief info about the linked product")
    link_type_idx: str = Field(description="Link type identifier", examples=["related"])
    link_type_name: str = Field(description="Link type display name", examples=["Related Products"])
    position: int = Field(description="Display order position", examples=[1])
    db_created: str = Field(description="Creation timestamp", examples=["2024-01-01T00:00:00Z"])


class ProductLinkListResponse(BaseModel):
    count: int = Field(description="Total number of product links", examples=[0, 5], ge=0)
    next: str | None = Field(None, description="URL to next page")
    previous: str | None = Field(None, description="URL to previous page")
    results: list[ProductLinkResponse] = Field(description="List of product link objects")

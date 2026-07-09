# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Response schemas for product link types."""

from pydantic import BaseModel, ConfigDict, Field


class ProductLinkTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(description="Primary key", examples=[1])
    idx: str = Field(description="Unique identifier", examples=["related"])
    name_t9n: dict = Field(
        description="Translated name JSON", examples=[{"en": "Related Products", "pl": "Powiązane produkty"}]
    )
    name: str = Field(description="Resolved name", examples=["Related Products"])
    desc: str = Field(
        "",
        description="Internal description / instruction. Used to ground AI workflows when matching (feature-set selection, attribute fill). Not shown on the storefront.",
        examples=["Accessories that fit the product; never link substitutes here."],
    )
    position: int = Field(description="Display order position", examples=[1])
    db_created: str = Field(description="Creation timestamp", examples=["2024-01-01T00:00:00Z"])


class ProductLinkTypeListResponse(BaseModel):
    count: int = Field(description="Total number of link types", examples=[0, 4], ge=0)
    next: str | None = Field(None, description="URL to next page")
    previous: str | None = Field(None, description="URL to previous page")
    results: list[ProductLinkTypeResponse] = Field(description="List of link type objects")

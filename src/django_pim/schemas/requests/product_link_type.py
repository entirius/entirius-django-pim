# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Request schemas for product link types."""

from pydantic import BaseModel, Field


class CreateProductLinkTypeRequest(BaseModel):
    idx: str = Field(
        description="Unique identifier for the link type", examples=["related"], min_length=1, max_length=64
    )
    name_t9n: dict = Field(
        description="Translated name JSON", examples=[{"en": "Related Products", "pl": "Powiązane produkty"}]
    )
    desc: str = Field(
        "",
        description="Internal description / instruction. Used to ground AI workflows when matching (feature-set selection, attribute fill). Not shown on the storefront.",
        examples=["Accessories that fit the product; never link substitutes here."],
    )
    position: int = Field(default=0, description="Display order position", examples=[1])


class UpdateProductLinkTypeRequest(BaseModel):
    name_t9n: dict | None = Field(None, description="Translated name JSON", examples=[{"en": "Related Products"}])
    desc: str | None = Field(
        None,
        description="Internal description / instruction. Used to ground AI workflows when matching (feature-set selection, attribute fill). Not shown on the storefront.",
        examples=["Accessories that fit the product; never link substitutes here."],
    )
    position: int | None = Field(None, description="Display order position", examples=[1])

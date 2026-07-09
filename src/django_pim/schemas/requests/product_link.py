# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Request schemas for product links."""

from pydantic import BaseModel, Field


class CreateProductLinkRequest(BaseModel):
    linked_product_sku: str = Field(description="SKU of the product to link to", examples=["CHAIR-002"], min_length=1)
    link_type_idx: str = Field(
        description="Link type identifier (e.g., related, crosssell, upsell)", examples=["related"], min_length=1
    )
    position: int = Field(default=1, description="Display order position", examples=[1])


class UpdateProductLinkRequest(BaseModel):
    link_type_idx: str | None = Field(None, description="Link type identifier", examples=["crosssell"])
    position: int | None = Field(None, description="Display order position", examples=[2])

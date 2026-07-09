# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Request schemas for product position in category."""

from pydantic import BaseModel, Field


class ProductPositionItem(BaseModel):
    """A single product position assignment."""

    sku: str = Field(description="Product SKU identifier", examples=["CHAIR-001"])
    position: int = Field(description="Position in category (0=unpositioned, >0=pinned)", ge=0, examples=[1])


class ProductPositionReorderRequest(BaseModel):
    """Request body for reordering products within a category."""

    items: list[ProductPositionItem] = Field(description="Products with their new positions")

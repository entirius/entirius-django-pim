# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Request schemas for product pictures."""

from pydantic import BaseModel, Field


class LinkPictureRequest(BaseModel):
    picture_pk: int = Field(description="Primary key of an existing Picture to link", examples=[1])
    picture_role: str = Field(
        default="general", description="Picture role: main, general, variant, angle", examples=["main"]
    )
    position: int = Field(default=0, description="Display order position", examples=[0])
    language_iso2: str | None = Field(None, description="Language ISO2 code (null = all languages)", examples=["en"])
    alt_text_t9n: dict = Field(
        default_factory=dict, description="Alt text translations", examples=[{"en": "Blue ergonomic chair"}]
    )


class UpdateProductPictureRequest(BaseModel):
    picture_role: str | None = Field(
        None, description="Picture role: main, general, variant, angle", examples=["general"]
    )
    position: int | None = Field(None, description="Display order position", examples=[1])
    language_iso2: str | None = Field(None, description="Language ISO2 code", examples=["en"])
    alt_text_t9n: dict | None = Field(None, description="Alt text translations", examples=[{"en": "Updated alt text"}])

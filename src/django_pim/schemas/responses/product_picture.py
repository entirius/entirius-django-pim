# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Response schemas for pictures and product pictures."""

from pydantic import BaseModel, ConfigDict, Field


class PictureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(description="Picture primary key", examples=[1])
    sha1: str | None = Field(
        description="SHA1 hash of the image file", examples=["a94a8fe5ccb19ba61c4c0873d391e987982fbbd3"]
    )
    width: int | None = Field(description="Image width in pixels", examples=[1920])
    height: int | None = Field(description="Image height in pixels", examples=[1080])
    original_file_name: str | None = Field(description="Original uploaded file name", examples=["chair-front.jpg"])
    image_url: str = Field(description="URL to the image file", examples=["/media/image/abc123.jpg"])
    db_created: str = Field(description="Creation timestamp", examples=["2024-01-01T00:00:00Z"])


class ProductPictureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(description="ProductPicture primary key", examples=[1])
    picture: PictureResponse = Field(description="Picture details")
    picture_role: str = Field(description="Picture role API label", examples=["main"])
    picture_role_name: str = Field(description="Picture role display name", examples=["Main Product Picture"])
    language_iso2: str | None = Field(description="Language ISO2 code (null = all languages)", examples=["en"])
    position: int = Field(description="Display order position", examples=[0])
    alt_text_t9n: dict = Field(description="Alt text translations", examples=[{"en": "Blue ergonomic chair"}])


class ProductPictureListResponse(BaseModel):
    count: int = Field(description="Total number of product pictures", examples=[0, 5], ge=0)
    next: str | None = Field(None, description="URL to next page")
    previous: str | None = Field(None, description="URL to previous page")
    results: list[ProductPictureResponse] = Field(description="List of product picture objects")

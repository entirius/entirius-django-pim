# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Request schemas for product videos."""

from pydantic import BaseModel, Field


class CreateProductVideoRequest(BaseModel):
    video_url: str = Field(
        description="Video URL (YouTube or Vimeo)",
        examples=["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
        min_length=1,
    )
    title: str | None = Field(None, description="Video title", examples=["Product Assembly Guide"])
    video_role: str = Field(default="unknown", description="Video role: main, variant, unknown", examples=["main"])
    language_iso2: str | None = Field(None, description="Language ISO2 code (null = all languages)", examples=["en"])
    position: int = Field(default=0, description="Display order position", examples=[0])


class UpdateProductVideoRequest(BaseModel):
    title: str | None = Field(None, description="Video title", examples=["Updated Title"])
    video_role: str | None = Field(None, description="Video role: main, variant, unknown", examples=["variant"])
    language_iso2: str | None = Field(None, description="Language ISO2 code", examples=["en"])
    position: int | None = Field(None, description="Display order position", examples=[1])

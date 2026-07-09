# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Response schemas for videos and product videos."""

from pydantic import BaseModel, ConfigDict, Field


class VideoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(description="Video primary key", examples=[1])
    title: str | None = Field(description="Video title", examples=["Product Assembly Guide"])
    is_external: bool = Field(description="Whether video URL is external", examples=[True])
    source: str = Field(description="Video source (youtube, vimeo, unknown)", examples=["youtube"])
    source_name: str = Field(description="Video source display name", examples=["YouTube"])
    video_url: str | None = Field(description="Video URL", examples=["https://www.youtube.com/watch?v=dQw4w9WgXcQ"])
    db_created: str = Field(description="Creation timestamp", examples=["2024-01-01T00:00:00Z"])


class ProductVideoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(description="ProductVideo primary key", examples=[1])
    video: VideoResponse = Field(description="Video details")
    video_role: str = Field(description="Video role API label", examples=["main"])
    video_role_name: str = Field(description="Video role display name", examples=["Main Product Video"])
    language_iso2: str | None = Field(description="Language ISO2 code (null = all languages)", examples=["en"])
    position: int = Field(description="Display order position", examples=[0])


class ProductVideoListResponse(BaseModel):
    count: int = Field(description="Total number of product videos", examples=[0, 3], ge=0)
    next: str | None = Field(None, description="URL to next page")
    previous: str | None = Field(None, description="URL to previous page")
    results: list[ProductVideoResponse] = Field(description="List of product video objects")

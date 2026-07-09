# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Request schemas for inheritance operations."""

from pydantic import BaseModel, Field


class CopyAttributesRequest(BaseModel):
    """Request to copy attributes from a source channel."""

    source_channel_idx: str = Field(
        description="Source channel idx to copy attributes from", examples=["default-local"], min_length=1
    )
    languages: list[str] | None = Field(
        None, description="Language codes to copy. Null copies all matching languages.", examples=[["en"]]
    )


# Backward-compatible alias
CopyTranslationsRequest = CopyAttributesRequest


class AddToChannelRequest(BaseModel):
    """Request to add a product to another channel."""

    target_channel_idx: str = Field(description="Target channel idx", examples=["default-europe"], min_length=1)
    copy_content: bool = Field(default=False, description="Whether to copy attribute values from source product")
    inherit_attributes: bool = Field(default=False, description="Inherit technical attributes from default channel")
    inherit_descriptions: bool = Field(
        default=False, description="Inherit name/description/short_description from default channel"
    )
    inherit_images: bool = Field(default=False, description="Inherit pictures, videos, and files from default channel")


class ToggleLanguageOverrideRequest(BaseModel):
    """Request to toggle language override for a specific attribute."""

    feature_idx: str = Field(description="Feature identifier", examples=["name"], min_length=1)
    language: str = Field(description="ISO 639-1 language code", examples=["en"], min_length=2, max_length=5)
    override: bool = Field(description="True = user controls this language, False = inherit from default channel")


class ToggleMediaOverrideRequest(BaseModel):
    """Request to toggle a media item between inherited and local."""

    picture_id: int | None = Field(None, description="ProductPicture PK to toggle", examples=[42])
    video_id: int | None = Field(None, description="ProductVideo PK to toggle", examples=[7])
    file_id: int | None = Field(None, description="ProductFile PK to toggle", examples=[3])
    override: bool = Field(description="True = make local (user controls), False = mark as inherited")

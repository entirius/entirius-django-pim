# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Response schemas for channels."""

from pydantic import BaseModel, ConfigDict, Field


class ChannelResponse(BaseModel):
    """Single channel response."""

    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(description="Primary key", examples=[1])
    idx: str = Field(description="Channel identifier", examples=["default"], min_length=1, max_length=128)
    name: str = Field(description="Channel display name", examples=["Default Channel"])
    default_language: str = Field(description="Default language ISO code", examples=["en"])
    default_currency: str = Field(description="Default currency code", examples=["EUR"])
    languages: list[str] = Field(description="Supported language ISO codes", examples=[["en", "pl"]])
    is_default: bool = Field(
        description="Whether this is the default channel for translation inheritance", examples=[True]
    )
    inheritance_enabled: bool = Field(description="Whether inheritance is enabled on this channel", examples=[False])
    default_inheritance_flags: list[str] = Field(
        default_factory=list,
        description="Default inheritance flags for new products on this channel",
        examples=[["attributes", "descriptions"]],
    )


class ChannelListResponse(BaseModel):
    """Paginated list of channels."""

    count: int = Field(description="Total count", examples=[0, 5], ge=0)
    next: str | None = Field(None, description="URL to next page")
    previous: str | None = Field(None, description="URL to previous page")
    results: list[ChannelResponse] = Field(description="List of channels")

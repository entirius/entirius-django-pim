# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""FeatureSet request schemas for django-pim Admin API v2."""

from pydantic import BaseModel, Field


class CreateFeatureSetRequest(BaseModel):
    """Request schema for creating a new feature set."""

    idx: str = Field(
        ...,
        description="Unique slug identifier for the feature set. Must be URL-safe and unique across all feature sets.",
        examples=["electronics", "clothing-apparel", "default"],
        min_length=1,
        max_length=256,
    )
    name: str = Field(
        "",
        description="Human-readable display name for the feature set.",
        examples=["Electronics Features", "Clothing & Apparel", "Default"],
        max_length=256,
    )
    desc: str = Field(
        "",
        description="Internal description of the feature set for editorial reference.",
        examples=["Feature set for all electronics products", ""],
    )
    is_default: bool = Field(
        False,
        description="Whether this feature set is the default applied to new products without an explicit assignment.",
        examples=[False, True],
    )


class UpdateFeatureSetRequest(BaseModel):
    """Request schema for updating an existing feature set. All fields are optional."""

    name: str | None = Field(
        None,
        description="Human-readable display name for the feature set.",
        examples=["Electronics Features", "Clothing & Apparel"],
        max_length=256,
    )
    desc: str | None = Field(
        None,
        description="Internal description of the feature set for editorial reference.",
        examples=["Feature set for all electronics products", ""],
    )
    is_default: bool | None = Field(
        None,
        description="Whether this feature set is the default applied to new products without an explicit assignment.",
        examples=[False, True],
    )

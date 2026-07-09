# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""AttributesGroup request schemas for django-pim Admin API v2."""

from pydantic import BaseModel, Field


class CreateAttributesGroupRequest(BaseModel):
    """Request schema for creating a new attributes group."""

    idx: str = Field(
        ...,
        description=(
            "Unique slug identifier for the attributes group. "
            "Used to assign attributes to this group via their group_idx field."
        ),
        examples=["warm-colors", "cool-colors", "standard-sizes", "premium-materials"],
        min_length=1,
        max_length=128,
    )
    name_t9n: dict = Field(
        ...,
        description=(
            "Translation dictionary mapping ISO 639-1 language codes to display names. "
            "At least one language entry is required."
        ),
        examples=[
            {"en": "Warm Colors", "pl": "Ciepłe Kolory"},
            {"en": "Standard Sizes"},
            {"en": "Premium Materials", "pl": "Materiały Premium"},
        ],
    )
    desc: str = Field(
        "",
        description="Internal description / instruction. Used to ground AI workflows when matching (feature-set selection, attribute fill). Not shown on the storefront.",
        examples=["Cluster of muted tones; use for textiles."],
    )


class UpdateAttributesGroupRequest(BaseModel):
    """Request schema for updating an existing attributes group. All fields are optional."""

    name_t9n: dict | None = Field(
        None,
        description=(
            "Translation dictionary mapping ISO 639-1 language codes to display names. "
            "Replaces the entire translation map when provided."
        ),
        examples=[{"en": "Warm Colors", "pl": "Ciepłe Kolory"}, {"en": "Standard Sizes"}],
    )
    desc: str | None = Field(
        None,
        description="Internal description / instruction. Used to ground AI workflows when matching (feature-set selection, attribute fill). Not shown on the storefront.",
        examples=["Cluster of muted tones; use for textiles."],
    )

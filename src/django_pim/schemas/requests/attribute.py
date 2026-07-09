# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Attribute request schemas for django-pim Admin API v2."""

from pydantic import BaseModel, Field


class CreateAttributeRequest(BaseModel):
    """Request schema for creating a new attribute under a feature."""

    feature_idx: str = Field(
        ...,
        description="Identifier of the parent feature. The attribute belongs to this feature's value set.",
        examples=["color", "size", "material"],
        min_length=1,
        max_length=128,
    )
    idx: str = Field(
        ...,
        description=(
            "Unique identifier for the attribute within its parent feature. Forms a composite key with feature_idx."
        ),
        examples=["red", "blue-ocean", "xl", "cotton"],
        min_length=1,
        max_length=128,
    )
    name_t9n: dict = Field(
        ...,
        description=(
            "Translation dictionary mapping ISO 639-1 language codes to display names. "
            "At least one language entry is required."
        ),
        examples=[{"en": "Red", "pl": "Czerwony"}, {"en": "XL"}, {"en": "Cotton", "pl": "Bawełna"}],
    )
    desc: str = Field(
        "",
        description="Internal description / instruction. Used to ground AI workflows when matching (feature-set selection, attribute fill). Not shown on the storefront.",
        examples=["RAL 9010 family; do not use for off-white."],
    )
    group_idx: str | None = Field(
        None,
        description=(
            "Identifier of the attributes group this attribute belongs to. "
            "Groups are used to cluster related attributes (e.g. 'warm-colors', 'cool-colors'). "
            "Null means no group assignment."
        ),
        examples=["warm-colors", "cool-colors", "standard-sizes", None],
    )
    display_order: int = Field(
        100,
        description=(
            "Sort order for displaying this attribute within its feature. Lower values appear first. Default is 100."
        ),
        examples=[100, 200, 50, 300],
        ge=0,
    )


class AttributeReorderItem(BaseModel):
    """Single item in a batch reorder request."""

    feature_idx: str = Field(..., description="Parent feature identifier", examples=["color"])
    idx: str = Field(..., description="Attribute identifier within the feature", examples=["red"])
    display_order: int = Field(..., description="New display order position", examples=[1, 2, 3], ge=0)


class AttributeReorderRequest(BaseModel):
    """Request schema for batch reordering attributes."""

    items: list[AttributeReorderItem] = Field(
        ..., description="List of attributes with their new display_order values", min_length=1
    )


class UpdateAttributeRequest(BaseModel):
    """Request schema for updating an existing attribute. All fields are optional."""

    name_t9n: dict | None = Field(
        None,
        description=(
            "Translation dictionary mapping ISO 639-1 language codes to display names. "
            "Replaces the entire translation map when provided."
        ),
        examples=[{"en": "Red", "pl": "Czerwony"}, {"en": "XL"}],
    )
    desc: str | None = Field(
        None,
        description="Internal description / instruction. Used to ground AI workflows when matching (feature-set selection, attribute fill). Not shown on the storefront.",
        examples=["RAL 9010 family; do not use for off-white."],
    )
    group_idx: str | None = Field(
        None,
        description=(
            "Identifier of the attributes group this attribute belongs to. Pass null to remove group assignment."
        ),
        examples=["warm-colors", "standard-sizes", None],
    )
    display_order: int | None = Field(
        None,
        description="Sort order for displaying this attribute within its feature. Lower values appear first.",
        examples=[100, 200, 50],
        ge=0,
    )

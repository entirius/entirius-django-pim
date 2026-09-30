# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Feature-in-FeatureSet bulk operation request schemas for django-pim Admin API v2."""

from pydantic import BaseModel, Field


class FeatureInSetEntry(BaseModel):
    """A single feature entry for bulk add operations, with optional position override."""

    feature_idx: str = Field(
        ...,
        description="Unique identifier of the feature to add to the set.",
        examples=["color", "size", "material"],
        min_length=1,
        max_length=128,
    )
    position: int | None = Field(
        None,
        description=(
            "Display position of the feature within the set. "
            "Lower values appear first. When omitted, position is auto-assigned "
            "as the next available slot starting at 500."
        ),
        examples=[500, 501, 600, None],
        ge=0,
    )
    attributes_group_idx: str | None = Field(
        None,
        description=("AttributesGroup idx to assign this feature to within the set. Null means no group assignment."),
        examples=["general", "dimensions", None],
    )
    is_required: bool | None = Field(
        None,
        description=(
            "Per-set override of Feature.is_required. Null (default) inherits the feature's flag; "
            "true/false applies to this set only. Rejected for SYSTEM-scope features."
        ),
        examples=[True, False, None],
    )


class BulkAddFeaturesRequest(BaseModel):
    """Request schema for bulk-adding features to a feature set."""

    features: list[FeatureInSetEntry] = Field(
        ...,
        description=(
            "List of features to add to the feature set. "
            "Features already present in the set are ignored (idempotent). "
            "Minimum one entry required."
        ),
        examples=[
            [
                {"feature_idx": "color", "position": 500},
                {"feature_idx": "size", "position": 501},
                {"feature_idx": "material", "position": None},
            ]
        ],
        min_length=1,
    )


class ReorderFeatureInSetEntry(BaseModel):
    """A single entry for reordering a feature within a set."""

    feature_idx: str = Field(..., description="Feature identifier", examples=["color"])
    position: int = Field(..., description="New position in the set", examples=[1, 2, 3], ge=0)
    attributes_group_idx: str | None = Field(
        None, description="AttributesGroup idx to assign (null to clear)", examples=["general", None]
    )


class ReorderFeaturesInSetRequest(BaseModel):
    """Request schema for reordering features within a feature set."""

    features: list[ReorderFeatureInSetEntry] = Field(
        ..., description="List of features with new positions and optional group assignments", min_length=1
    )


class BulkRemoveFeaturesRequest(BaseModel):
    """Request schema for bulk-removing features from a feature set."""

    feature_idxs: list[str] = Field(
        ...,
        description=(
            "List of feature identifiers to remove from the feature set. "
            "Features not present in the set are ignored (idempotent). "
            "Minimum one entry required."
        ),
        examples=[["color", "size"], ["material"]],
        min_length=1,
    )


class SetFeatureRequiredRequest(BaseModel):
    """Request schema for setting the per-set required override of one feature in a set."""

    is_required: bool | None = Field(
        ...,
        description=(
            "true/false overrides Feature.is_required for this set only; null clears the override "
            "(inherit the feature's flag). The key is required. Rejected for SYSTEM-scope features."
        ),
        examples=[True, False, None],
    )

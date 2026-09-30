# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""FeatureSet response schemas for django-pim APIs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from .feature import FeatureResponse


class FeatureSetResponse(BaseModel):
    """
    Response schema for a single feature set.

    Contains feature set information with feature count.
    """

    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(..., description="FeatureSet primary key", examples=[1, 42, 123])
    idx: str = Field(
        ...,
        description="FeatureSet unique identifier (slug)",
        examples=["default", "electronics", "clothing"],
        min_length=1,
        max_length=256,
    )
    name: str = Field(
        ...,
        description="FeatureSet name",
        examples=["Default", "Electronics Features", "Clothing Features"],
        max_length=256,
    )
    desc: str = Field(
        "", description="FeatureSet description for internal use", examples=["Default feature set for all products", ""]
    )
    is_default: bool = Field(..., description="Whether this is the default feature set", examples=[True, False])
    feature_count: int = Field(0, description="Number of features in this set", examples=[0, 10, 50], ge=0)


class FeatureSetListResponse(BaseModel):
    """
    Response schema for paginated feature set list.

    Contains pagination metadata and list of feature sets.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Total number of feature sets matching the query", examples=[0, 5, 20], ge=0)
    next: str | None = Field(
        None,
        description="URL to next page of results (null if no next page)",
        examples=["/api/pim/admin/feature-sets/?page=2", None],
    )
    previous: str | None = Field(
        None,
        description="URL to previous page of results (null if no previous page)",
        examples=["/api/pim/admin/feature-sets/?page=1", None],
    )
    results: list[FeatureSetResponse] = Field(
        ..., description="List of feature sets in the current page", examples=[[]]
    )


class FeatureInSetResponse(BaseModel):
    """
    Response schema for a feature within a feature set.

    Extends FeatureResponse with position and group information.
    """

    model_config = ConfigDict(from_attributes=True)

    position: int = Field(..., description="Position/order of feature within the set", examples=[500, 501, 600], ge=0)
    attributes_group_idx: str | None = Field(
        None,
        description="AttributesGroup idx this feature is assigned to within the set",
        examples=["general", "dimensions", None],
    )
    attributes_group_name: str | None = Field(
        None,
        description="AttributesGroup display name (resolved from name_t9n)",
        examples=["General", "Dimensions", None],
    )
    is_required: bool = Field(
        ...,
        description=(
            "Effective required flag in this set: the per-set override when set, otherwise Feature.is_required"
        ),
        examples=[True, False],
    )
    is_required_override: bool | None = Field(
        None,
        description="Raw per-set override (null = inherits Feature.is_required)",
        examples=[True, False, None],
    )
    feature: FeatureResponse = Field(..., description="Feature details")


class FeaturesInSetListResponse(BaseModel):
    """
    Response schema for paginated list of features in a feature set.

    Contains pagination metadata and list of features with positions.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Total number of features in the set", examples=[0, 10, 50], ge=0)
    next: str | None = Field(
        None,
        description="URL to next page of results (null if no next page)",
        examples=["/api/pim/admin/feature-sets/default/features/?page=2", None],
    )
    previous: str | None = Field(
        None,
        description="URL to previous page of results (null if no previous page)",
        examples=["/api/pim/admin/feature-sets/default/features/?page=1", None],
    )
    results: list[FeatureInSetResponse] = Field(
        ..., description="List of features with positions in the current page", examples=[[]]
    )


class RequiredFeatureResponse(BaseModel):
    """A feature a product of the set must carry, with where the requirement comes from."""

    model_config = ConfigDict(from_attributes=True)

    feature: FeatureResponse = Field(..., description="Feature details")
    source: Literal["system", "feature", "feature_set"] = Field(
        ...,
        description=(
            "system: SYSTEM-scope feature flagged required (applies to every set); "
            "feature: inherited Feature.is_required; feature_set: per-set override true"
        ),
        examples=["feature"],
    )


class RequiredFeatureListResponse(RootModel[list[RequiredFeatureResponse]]):
    """Bare JSON array of required features (not paginated). Root model so OpenAPI can name it."""

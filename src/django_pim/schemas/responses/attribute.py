# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Attribute response schemas for django-pim APIs."""

from pydantic import BaseModel, ConfigDict, Field


class AttributeResponse(BaseModel):
    """
    Response schema for a single attribute.

    Contains attribute information including translated name
    and references to feature and group.
    """

    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(..., description="Attribute primary key", examples=[1, 42, 123])
    feature_idx: str = Field(
        ...,
        description="Parent feature identifier (part of composite key)",
        examples=["color", "size", "material"],
        max_length=128,
    )
    idx: str = Field(
        ...,
        description="Attribute identifier within feature (part of composite key)",
        examples=["red", "blue", "large", "small"],
        min_length=1,
        max_length=128,
    )
    name: str = Field(
        ...,
        description="Attribute name (translated for shop language)",
        examples=["Red", "Blue", "Large", "Small"],
        min_length=1,
    )
    name_t9n: dict = Field(
        default_factory=dict,
        description="Translation dictionary mapping ISO 639-1 language codes to display names",
        examples=[{"en": "Red", "pl": "Czerwony"}],
    )
    desc: str = Field(
        "",
        description="Internal description / instruction. Used to ground AI workflows when matching (feature-set selection, attribute fill). Not shown on the storefront.",
        examples=["RAL 9010 family; do not use for off-white."],
    )
    group_idx: str | None = Field(
        None, description="Attributes group identifier (null if no group)", examples=["primary-colors", "sizes", None]
    )
    display_order: int = Field(..., description="Display order for sorting attributes", examples=[100, 200, 300], ge=0)


class AttributeListResponse(BaseModel):
    """
    Response schema for paginated attribute list.

    Contains pagination metadata and list of attributes.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Total number of attributes matching the query", examples=[0, 10, 150], ge=0)
    next: str | None = Field(
        None,
        description="URL to next page of results (null if no next page)",
        examples=["/api/pim/admin/attributes/?page=2", None],
    )
    previous: str | None = Field(
        None,
        description="URL to previous page of results (null if no previous page)",
        examples=["/api/pim/admin/attributes/?page=1", None],
    )
    results: list[AttributeResponse] = Field(..., description="List of attributes in the current page", examples=[[]])

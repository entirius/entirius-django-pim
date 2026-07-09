# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""AttributesGroup response schemas for django-pim APIs."""

from pydantic import BaseModel, ConfigDict, Field


class AttributesGroupResponse(BaseModel):
    """
    Response schema for a single attributes group.

    Contains group information including translated name
    and optional attribute count.
    """

    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(..., description="AttributesGroup primary key", examples=[1, 42, 123])
    idx: str = Field(
        ...,
        description="AttributesGroup unique identifier",
        examples=["light-colors", "dark-colors", "sizes"],
        min_length=1,
        max_length=128,
    )
    name: str = Field(
        ...,
        description="AttributesGroup name (translated)",
        examples=["Light Colors", "Dark Colors", "Sizes"],
        min_length=1,
    )
    desc: str = Field(
        "",
        description="Internal description / instruction. Used to ground AI workflows when matching (feature-set selection, attribute fill). Not shown on the storefront.",
        examples=["Cluster of muted tones; use for textiles."],
    )
    attribute_count: int = Field(0, description="Number of attributes in this group", examples=[0, 5, 10], ge=0)


class AttributesGroupListResponse(BaseModel):
    """
    Response schema for paginated attributes group list.

    Contains pagination metadata and list of groups.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Total number of groups matching the query", examples=[0, 5, 20], ge=0)
    next: str | None = Field(
        None,
        description="URL to next page of results (null if no next page)",
        examples=["/api/pim/admin/attributes-groups/?page=2", None],
    )
    previous: str | None = Field(
        None,
        description="URL to previous page of results (null if no previous page)",
        examples=["/api/pim/admin/attributes-groups/?page=1", None],
    )
    results: list[AttributesGroupResponse] = Field(
        ..., description="List of attributes groups in the current page", examples=[[]]
    )

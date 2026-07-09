# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Request schemas for the quality-gaps admin API (etap-04).

GapDefinition is the per-client config of one quality check. Validation of ``check_key`` /
``params`` against the registry allowlist happens in the service layer (``gap_definition_service``),
not here — these schemas only enforce shape + required fields at the API boundary.
"""

from pydantic import BaseModel, Field


class CreateGapDefinitionRequest(BaseModel):
    """Request schema for creating a gap definition."""

    key: str = Field(
        description="Unique rule identifier (slug)", examples=["pl-description"], min_length=1, max_length=64
    )
    check_key: str = Field(
        description="Registry check key", examples=["feature_present", "feature_min_length", "picture_present"]
    )
    params: dict = Field(default_factory=dict, description="Check params", examples=[{"feature_idx": "description"}])
    languages: list[str] | None = Field(None, description="Restrict to languages (null = all channel languages)")
    channels: list[str] | None = Field(None, description="Restrict to channels (null = all)")
    severity: str = Field(description="Severity", examples=["critical", "warning"])
    label_t9n: dict = Field(
        default_factory=dict, description="Translated UI label", examples=[{"en": "Missing description"}]
    )
    active: bool = Field(True, description="Whether the rule is active")
    display_order: int = Field(0, description="Sort position in the rules UI")


class UpdateGapDefinitionRequest(BaseModel):
    """Request schema for updating a gap definition (PATCH — all fields optional, ``key`` immutable)."""

    check_key: str | None = Field(None, description="Registry check key")
    params: dict | None = Field(None, description="Check params")
    languages: list[str] | None = Field(None, description="Restrict to languages (null = all channel languages)")
    channels: list[str] | None = Field(None, description="Restrict to channels (null = all)")
    severity: str | None = Field(None, description="Severity (critical|warning)")
    label_t9n: dict | None = Field(None, description="Translated UI label")
    active: bool | None = Field(None, description="Whether the rule is active")
    display_order: int | None = Field(None, description="Sort position in the rules UI")

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Response schemas for the quality-gaps admin API (etap-04).

Covers: GapDefinition CRUD, the per-page bulk findings endpoint, the recompute trigger, and the
"rules changed vs recomputed" status that drives the CMS alert.
"""

from pydantic import BaseModel, ConfigDict, Field


class GapDefinitionResponse(BaseModel):
    """A single gap definition (rule)."""

    model_config = ConfigDict(from_attributes=True)

    key: str = Field(description="Unique rule identifier", examples=["pl-description"])
    check_key: str = Field(description="Registry check key", examples=["feature_present"])
    params: dict = Field(default_factory=dict, description="Check params", examples=[{"feature_idx": "description"}])
    languages: list[str] | None = Field(None, description="Restricted languages (null = all channel languages)")
    channels: list[str] | None = Field(None, description="Restricted channels (null = all)")
    severity: str = Field(description="Severity", examples=["critical", "warning"])
    label_t9n: dict = Field(
        default_factory=dict, description="Translated UI label", examples=[{"en": "Missing description"}]
    )
    active: bool = Field(description="Whether the rule is active")
    display_order: int = Field(description="Sort position in the rules UI")
    created_at: str | None = Field(None, description="ISO8601 creation timestamp")
    modified_at: str | None = Field(None, description="ISO8601 last-modified timestamp")


class GapDefinitionListResponse(BaseModel):
    """Paginated list of gap definitions."""

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(description="Total number of definitions matching the query", ge=0)
    next: str | None = Field(None, description="URL to next page (null if none)")
    previous: str | None = Field(None, description="URL to previous page (null if none)")
    results: list[GapDefinitionResponse] = Field(description="Definitions in the current page")


class GapFindingResponse(BaseModel):
    """A single open gap on a product (one missing thing, in one language)."""

    model_config = ConfigDict(from_attributes=True)

    definition_key: str = Field(description="Rule that flagged this gap", examples=["pl-description"])
    label_t9n: dict = Field(default_factory=dict, description="Translated label (from the rule)")
    severity: str = Field(description="Severity", examples=["critical", "warning"])
    language: str | None = Field(None, description="Language of the gap (null = language-neutral, e.g. pictures)")
    inherited: bool = Field(description="Whether the value is inherited/locked from the default channel")
    source_channel: str | None = Field(None, description="Where to fix it when inherited (null otherwise)")


class GapFindingsBulkResponse(BaseModel):
    """Findings for a page of products, keyed by product PK (as string).

    Sparse: products with no gaps are absent — the CMS treats a missing key as zero gaps.
    """

    results: dict[str, list[GapFindingResponse]] = Field(
        default_factory=dict, description="product_pk -> list of gaps", examples=[{"42": []}]
    )


class GapExemptionResponse(BaseModel):
    """One per-product rule mute."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Exemption PK (used to delete)")
    sku: str = Field(description="Product SKU", examples=["SKU-1"])
    definition_key: str = Field(description="Muted rule", examples=["pl-description"])
    language: str | None = Field(None, description="Muted language (null = all languages)")
    reason: str = Field("", description="Operator's note")
    created_by_id: int | None = Field(None, description="User who created the exemption")
    created_at: str | None = Field(None, description="ISO8601 creation timestamp")


class GapExemptionListResponse(BaseModel):
    """All exemptions of one product (small set — no pagination)."""

    results: list[GapExemptionResponse] = Field(default_factory=list, description="Exemptions, newest first")


class GapRecomputeResponse(BaseModel):
    """Result of the 'recompute now' trigger."""

    status: str = Field(description="started | already_running", examples=["started", "already_running"])
    running: bool = Field(description="Whether a full recompute is in progress")


class GapSettingsResponse(BaseModel):
    """Operator-tunable gap settings (featureset-cascade etap-04)."""

    gaps_skip_default_featureset: bool = Field(
        description=(
            "While a product is on the default (placeholder) feature set, report only the "
            "'assign a real feature set' gap and suppress all other checks."
        )
    )


class GapStatusResponse(BaseModel):
    """Rules-changed vs recomputed signal for the CMS alert."""

    model_config = ConfigDict(from_attributes=True)

    gaps_enabled: bool = Field(description="Whether automatic gap recompute is enabled")
    rules_changed_at: str | None = Field(None, description="ISO8601 when rules last changed (null = never)")
    recomputed_at: str | None = Field(None, description="ISO8601 when the catalogue was last fully recomputed")
    is_stale: bool = Field(description="True when rules changed after the last full recompute")
    recompute_running: bool = Field(description="Whether a full recompute is currently in progress")

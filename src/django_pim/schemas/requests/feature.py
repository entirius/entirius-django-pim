# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Feature request schemas for django-pim Admin API v2.

Scope enum values:
  1 = SYSTEM
  2 = GLOBAL
  3 = BUSINESS_UNIT

FeatureType enum values:
  0 = UNKNOWN, 1 = BOOL, 2 = DECIMAL, 3 = VARCHAR255, 4 = VARCHAR255_T9N,
  5 = TEXT, 6 = TEXT_T9N, 7 = SELECT, 8 = MULTISELECT, 9 = JSON,
  10 = DATETIME, 11 = JSON_T9N, 12 = TEMPERATURE, 13 = LENGTH, 14 = MASS

FrontendInputType enum values:
  0 = DEFAULT, 1 = SELECT_SWATCH_VISUAL, 2 = SELECT_SWATCH_TEXT,
  3 = DROPDOWN, 4 = DROPDOWN_WITH_PRICE, 5 = PALETTE_COLOR,
  6 = SLIDER, 7 = BOOLEAN, 8 = RADIO

FilterType enum values:
  0 = DEFAULT, 1 = SELECT_SWATCH_IMAGE, 2 = SELECT_SWATCH_TEXT,
  3 = SLIDE, 4 = BOOLEAN, 5 = RADIO_TEXT
"""

from pydantic import BaseModel, Field


class CreateFeatureRequest(BaseModel):
    """Request schema for creating a new feature."""

    idx: str = Field(
        ...,
        description="Unique slug identifier for the feature. Used as a permanent key across translations.",
        examples=["color", "material", "screen-size"],
        min_length=1,
        max_length=128,
    )
    name_t9n: dict = Field(
        ...,
        description=(
            "Translation dictionary mapping ISO 639-1 language codes to display names. "
            "At least one language entry is required."
        ),
        examples=[{"en": "Color", "pl": "Kolor"}, {"en": "Material"}],
    )
    desc: str = Field(
        "",
        description="Internal description / instruction. Used to ground AI workflows when matching (feature-set selection, attribute fill). Not shown on the storefront.",
        examples=["Dominant case colour; pick the closest plain colour, no marketing names."],
    )
    scope: int = Field(
        3,
        description=(
            "Feature visibility scope. "
            "1 = SYSTEM (reserved, cannot be set via API), "
            "2 = GLOBAL (DEPRECATED — will be rejected), "
            "3 = BUSINESS_UNIT (default)."
        ),
        examples=[3],
        ge=2,
        le=3,
    )
    feature_type: int = Field(
        0,
        description=(
            "Data type of feature values. "
            "0 = UNKNOWN, 1 = BOOL, 2 = DECIMAL, 3 = VARCHAR255, 4 = VARCHAR255_T9N, "
            "5 = TEXT, 6 = TEXT_T9N, 7 = SELECT, 8 = MULTISELECT, 9 = JSON, "
            "10 = DATETIME, 11 = JSON_T9N, 12 = TEMPERATURE, 13 = LENGTH, 14 = MASS."
        ),
        examples=[7, 8, 2, 1, 0],
        ge=0,
        le=14,
    )
    frontend_input_type: int = Field(
        0,
        description=(
            "Frontend rendering hint for input widgets. "
            "0 = DEFAULT, 1 = SELECT_SWATCH_VISUAL, 2 = SELECT_SWATCH_TEXT, "
            "3 = DROPDOWN, 4 = DROPDOWN_WITH_PRICE, 5 = PALETTE_COLOR, "
            "6 = SLIDER, 7 = BOOLEAN, 8 = RADIO."
        ),
        examples=[0, 1, 3, 7],
        ge=0,
        le=8,
    )
    filter_type: int = Field(
        0,
        description=(
            "Filter widget type used in storefront faceted search. "
            "0 = DEFAULT, 1 = SELECT_SWATCH_IMAGE, 2 = SELECT_SWATCH_TEXT, "
            "3 = SLIDE, 4 = BOOLEAN, 5 = RADIO_TEXT."
        ),
        examples=[0, 1, 3, 4],
        ge=0,
        le=5,
    )
    display_order: int | None = Field(
        None,
        description=(
            "Sort order for displaying features in catalog and admin UI. "
            "Lower values appear first. Defaults to scope-based priority when omitted."
        ),
        examples=[10, 90, 110],
        ge=0,
    )
    is_required: bool = Field(
        False, description="Whether a value for this feature is required on every product.", examples=[False, True]
    )
    is_visible: bool = Field(
        True, description="Whether this feature is visible on product detail pages.", examples=[True, False]
    )
    is_filterable: bool = Field(
        False, description="Whether this feature can be used as a storefront filter facet.", examples=[False, True]
    )
    is_searchable: bool = Field(
        True,
        description="Whether attribute values for this feature are indexed for full-text search.",
        examples=[True, False],
    )
    is_comparable: bool = Field(
        False, description="Whether this feature appears in product comparison tables.", examples=[False, True]
    )
    is_for_customization: bool = Field(
        False,
        description="Whether this feature drives product customization options (e.g. engraving, custom color).",
        examples=[False, True],
    )
    exclude_from_inheritance: bool = Field(
        False,
        description="When true, this feature is never inherited — always independent per channel.",
        examples=[False, True],
    )
    has_visual_asset: bool = Field(
        False,
        description="When true, this feature's attribute values carry associated visual assets (icon, swatch, badge).",
        examples=[False, True],
    )
    is_seo: bool = Field(
        False,
        description="When true, this feature is an SEO metadata field (meta_title, meta_description, canonical_url, og_image).",
        examples=[False, True],
    )


class UpdateFeatureRequest(BaseModel):
    """Request schema for updating an existing feature. All fields are optional."""

    name_t9n: dict | None = Field(
        None,
        description=(
            "Translation dictionary mapping ISO 639-1 language codes to display names. "
            "Replaces the entire translation map when provided."
        ),
        examples=[{"en": "Color", "pl": "Kolor"}, {"en": "Material"}],
    )
    desc: str | None = Field(
        None,
        description="Internal description / instruction. Used to ground AI workflows when matching (feature-set selection, attribute fill). Not shown on the storefront.",
        examples=["Dominant case colour; pick the closest plain colour, no marketing names."],
    )
    scope: int | None = Field(
        None,
        description=(
            "Feature visibility scope. "
            "1 = SYSTEM (reserved, cannot be set via API), "
            "2 = GLOBAL (DEPRECATED — will be rejected), "
            "3 = BUSINESS_UNIT (default)."
        ),
        examples=[3],
        ge=2,
        le=3,
    )
    feature_type: int | None = Field(
        None,
        description=(
            "Data type of feature values. "
            "0 = UNKNOWN, 1 = BOOL, 2 = DECIMAL, 3 = VARCHAR255, 4 = VARCHAR255_T9N, "
            "5 = TEXT, 6 = TEXT_T9N, 7 = SELECT, 8 = MULTISELECT, 9 = JSON, "
            "10 = DATETIME, 11 = JSON_T9N, 12 = TEMPERATURE, 13 = LENGTH, 14 = MASS."
        ),
        examples=[7, 8, 2],
        ge=0,
        le=14,
    )
    frontend_input_type: int | None = Field(
        None,
        description=(
            "Frontend rendering hint for input widgets. "
            "0 = DEFAULT, 1 = SELECT_SWATCH_VISUAL, 2 = SELECT_SWATCH_TEXT, "
            "3 = DROPDOWN, 4 = DROPDOWN_WITH_PRICE, 5 = PALETTE_COLOR, "
            "6 = SLIDER, 7 = BOOLEAN, 8 = RADIO."
        ),
        examples=[0, 1, 3],
        ge=0,
        le=8,
    )
    filter_type: int | None = Field(
        None,
        description=(
            "Filter widget type used in storefront faceted search. "
            "0 = DEFAULT, 1 = SELECT_SWATCH_IMAGE, 2 = SELECT_SWATCH_TEXT, "
            "3 = SLIDE, 4 = BOOLEAN, 5 = RADIO_TEXT."
        ),
        examples=[0, 1, 3],
        ge=0,
        le=5,
    )
    display_order: int | None = Field(
        None, description="Sort order for displaying features. Lower values appear first.", examples=[10, 90, 110], ge=0
    )
    is_required: bool | None = Field(
        None, description="Whether a value for this feature is required on every product.", examples=[False, True]
    )
    is_visible: bool | None = Field(
        None, description="Whether this feature is visible on product detail pages.", examples=[True, False]
    )
    is_filterable: bool | None = Field(
        None, description="Whether this feature can be used as a storefront filter facet.", examples=[False, True]
    )
    is_searchable: bool | None = Field(
        None,
        description="Whether attribute values for this feature are indexed for full-text search.",
        examples=[True, False],
    )
    is_comparable: bool | None = Field(
        None, description="Whether this feature appears in product comparison tables.", examples=[False, True]
    )
    is_for_customization: bool | None = Field(
        None, description="Whether this feature drives product customization options.", examples=[False, True]
    )
    exclude_from_inheritance: bool | None = Field(
        None,
        description="When true, this feature is never inherited — always independent per channel.",
        examples=[False, True],
    )
    has_visual_asset: bool | None = Field(
        None,
        description="When true, this feature's attribute values carry associated visual assets (icon, swatch, badge).",
        examples=[False, True],
    )
    is_seo: bool | None = Field(
        None, description="When true, this feature is an SEO metadata field.", examples=[False, True]
    )

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Feature response schemas for django-pim APIs."""

from pydantic import BaseModel, ConfigDict, Field


class FeatureResponse(BaseModel):
    """
    Response schema for a single feature.

    Contains comprehensive feature information including
    translated names and enum labels.
    """

    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(..., description="Feature primary key", examples=[1, 42, 123])
    idx: str = Field(
        ...,
        description="Feature unique identifier (slug)",
        examples=["color", "size", "material"],
        min_length=1,
        max_length=128,
    )
    name: str = Field(
        ...,
        description="Feature name (translated for shop language)",
        examples=["Color", "Size", "Material"],
        min_length=1,
    )
    name_t9n: dict = Field(
        default_factory=dict,
        description="Translation dictionary mapping ISO 639-1 language codes to display names",
        examples=[{"en": "Color", "pl": "Kolor"}],
    )
    desc: str = Field(
        "",
        description="Internal description / instruction. Used to ground AI workflows when matching (feature-set selection, attribute fill). Not shown on the storefront.",
        examples=["Dominant case colour; pick the closest plain colour, no marketing names."],
    )
    scope: int = Field(
        ..., description="Feature scope enum value (1=SYSTEM, 2=GLOBAL, 3=BUSINESS_UNIT)", examples=[1, 2, 3]
    )
    scope_name: str = Field(..., description="Feature scope label", examples=["system", "global", "business unit"])
    feature_type: int = Field(..., description="Feature type enum value", examples=[1, 2, 3, 7, 8])
    feature_type_name: str = Field(
        ..., description="Feature type label", examples=["Bool", "Decimal", "Select", "Multiselect"]
    )
    frontend_input_type: int = Field(..., description="Frontend input type enum value", examples=[0, 1, 3, 7])
    frontend_input_type_name: str = Field(
        ..., description="Frontend input type label", examples=["Default", "Swatch_Visual", "dropdown", "boolean"]
    )
    filter_type: int = Field(..., description="Filter type enum value", examples=[0, 1, 3, 4])
    filter_type_name: str = Field(
        ..., description="Filter type label", examples=["Default", "Swatch_Image", "Slide", "Boolean"]
    )
    display_order: int = Field(..., description="Display order for sorting features", examples=[10, 90, 110], ge=0)
    is_required: bool = Field(..., description="Whether the feature is required", examples=[True, False])
    is_visible: bool = Field(..., description="Whether the feature is visible", examples=[True, False])
    is_filterable: bool = Field(..., description="Whether the feature can be used in filters", examples=[True, False])
    is_searchable: bool = Field(..., description="Whether the feature is searchable", examples=[True, False])
    is_comparable: bool = Field(
        ..., description="Whether the feature can be used for product comparison", examples=[True, False]
    )
    is_for_customization: bool = Field(
        ..., description="Whether the feature is for product customization", examples=[True, False]
    )
    exclude_from_inheritance: bool = Field(
        ...,
        description="When true, this feature is never inherited — always independent per channel",
        examples=[False, True],
    )
    has_visual_asset: bool = Field(
        ...,
        description="When true, this feature's attribute values carry associated visual assets (icon, swatch, badge)",
        examples=[False, True],
    )
    is_seo: bool = Field(
        ...,
        description="When true, this feature is an SEO metadata field (meta_title, meta_description, etc.)",
        examples=[False, True],
    )
    is_system: bool = Field(
        ...,
        description=(
            "Whether this is a protected system feature (scope=SYSTEM). "
            "System features cannot be deleted or have their type, scope, or required status changed."
        ),
        examples=[True, False],
    )


class FeatureListResponse(BaseModel):
    """
    Response schema for paginated feature list.

    Contains pagination metadata and list of features.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Total number of features matching the query", examples=[0, 10, 150], ge=0)
    next: str | None = Field(
        None,
        description="URL to next page of results (null if no next page)",
        examples=["/api/pim/admin/shop/features/?page=2", None],
    )
    previous: str | None = Field(
        None,
        description="URL to previous page of results (null if no previous page)",
        examples=["/api/pim/admin/shop/features/?page=1", None],
    )
    results: list[FeatureResponse] = Field(..., description="List of features in the current page", examples=[[]])

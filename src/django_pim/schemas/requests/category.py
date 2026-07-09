# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Category request schemas for django-pim Admin API v2."""

from pydantic import BaseModel, Field


class CreateCategoryRequest(BaseModel):
    """Request schema for creating a new category."""

    idx: str = Field(
        description="Category identifier (slug), must be unique within the channel",
        examples=["electronics"],
        min_length=1,
        max_length=128,
    )
    name_t9n: dict = Field(
        description="Translated category names", examples=[{"en": "Electronics", "pl": "Elektronika"}]
    )
    desc: str = Field(
        "",
        description="Internal description / instruction. Used to ground AI workflows when matching (feature-set selection, attribute fill). Not shown on the storefront.",
        examples=["Hand tools only; powered tools belong under power-tools."],
    )
    description_t9n: dict = Field(
        default_factory=dict,
        description="Translated category descriptions",
        examples=[{"en": "All electronics products"}],
    )
    meta_title_t9n: dict = Field(
        default_factory=dict, description="Translated SEO meta titles", examples=[{"en": "Electronics Store"}]
    )
    meta_description_t9n: dict = Field(
        default_factory=dict,
        description="Translated SEO meta descriptions",
        examples=[{"en": "Browse our electronics catalog"}],
    )
    canonical_url_t9n: dict = Field(
        default_factory=dict,
        description="Translated canonical URLs for SEO",
        examples=[{"en": "https://example.com/electronics"}],
    )
    image_url: str = Field(
        "", description="Category image URL", examples=["https://example.com/images/electronics.jpg"], max_length=512
    )
    og_image_url: str = Field(
        "",
        description="Open Graph image URL for social sharing previews",
        examples=["https://example.com/images/electronics-og.jpg"],
        max_length=512,
    )
    noindex: bool = Field(False, description="Whether search engines should not index this category", examples=[False])
    nofollow: bool = Field(
        False, description="Whether search engines should not follow links on this category", examples=[False]
    )
    parent_category_idx: str | None = Field(
        None, description="Parent category idx (null for root categories)", examples=[None, "root-category"]
    )
    position: int | None = Field(None, description="Sort position within siblings", examples=[10])
    is_active: bool = Field(True, description="Whether category is active", examples=[True])
    is_in_menu: bool = Field(True, description="Whether category appears in navigation menu", examples=[True])


class UpdateCategoryRequest(BaseModel):
    """Request schema for updating a category (PATCH - all fields optional)."""

    name_t9n: dict | None = Field(
        None, description="Translated category names", examples=[{"en": "Electronics", "pl": "Elektronika"}]
    )
    desc: str | None = Field(
        None,
        description="Internal description / instruction. Used to ground AI workflows when matching (feature-set selection, attribute fill). Not shown on the storefront.",
        examples=["Hand tools only; powered tools belong under power-tools."],
    )
    description_t9n: dict | None = Field(
        None, description="Translated category descriptions", examples=[{"en": "All electronics products"}]
    )
    meta_title_t9n: dict | None = Field(
        None, description="Translated SEO meta titles", examples=[{"en": "Electronics Store"}]
    )
    meta_description_t9n: dict | None = Field(
        None, description="Translated SEO meta descriptions", examples=[{"en": "Browse our electronics catalog"}]
    )
    canonical_url_t9n: dict | None = Field(
        None, description="Translated canonical URLs for SEO", examples=[{"en": "https://example.com/electronics"}]
    )
    image_url: str | None = Field(
        None, description="Category image URL", examples=["https://example.com/images/electronics.jpg"], max_length=512
    )
    og_image_url: str | None = Field(
        None,
        description="Open Graph image URL for social sharing previews",
        examples=["https://example.com/images/electronics-og.jpg"],
        max_length=512,
    )
    noindex: bool | None = Field(
        None, description="Whether search engines should not index this category", examples=[False]
    )
    nofollow: bool | None = Field(
        None, description="Whether search engines should not follow links on this category", examples=[False]
    )
    parent_category_idx: str | None = Field(
        None, description="Parent category idx (null to make root category)", examples=[None, "root-category"]
    )
    position: int | None = Field(None, description="Sort position within siblings", examples=[10])
    is_active: bool | None = Field(None, description="Whether category is active", examples=[True])
    is_in_menu: bool | None = Field(None, description="Whether category appears in navigation menu", examples=[True])


class CategoryReorderItem(BaseModel):
    """Single item in a category reorder request."""

    idx: str = Field(description="Category idx", examples=["electronics"])
    parent_category_idx: str | None = Field(
        None, description="New parent category idx (null = make root)", examples=[None, "root-category"]
    )
    position: int = Field(description="New position among siblings", examples=[10])


class CategoryReorderRequest(BaseModel):
    """Request to batch reorder categories."""

    items: list[CategoryReorderItem] = Field(description="List of categories with their new positions and parents")

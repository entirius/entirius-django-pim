# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Category response schemas for django-pim APIs."""

from pydantic import BaseModel, ConfigDict, Field


class CategoryResponse(BaseModel):
    """
    Response schema for a single product category.

    Contains essential category information for API responses.
    """

    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(..., description="Category primary key", examples=[1, 42, 123])
    idx: str = Field(
        ...,
        description="Category unique identifier (slug)",
        examples=["electronics", "clothing", "home-garden"],
        min_length=1,
        max_length=128,
    )
    name: str = Field(
        ...,
        description="Category name",
        examples=["Electronics", "Clothing", "Home & Garden"],
        min_length=1,
        max_length=500,
    )
    parent_category: int | None = Field(
        None, description="Parent category ID (null for root categories)", examples=[None, 1, 5]
    )
    is_active: bool = Field(..., description="Whether the category is active and visible", examples=[True, False])
    is_in_menu: bool = Field(..., description="Whether the category appears in navigation menu", examples=[True, False])
    url_key: str = Field(
        "",
        description="Storefront routing slug for the channel's default language (the key Matrix filters by); falls back to idx",
        examples=["all-fabrics"],
    )
    product_count: int = Field(0, description="Number of products in this category", examples=[0, 12], ge=0)
    desc: str = Field(
        "",
        description="Internal description / instruction. Used to ground AI workflows when matching (feature-set selection, attribute fill). Not shown on the storefront.",
        examples=["Hand tools only; powered tools belong under power-tools."],
    )


class CategoryListResponse(BaseModel):
    """
    Response schema for paginated category list.

    Contains pagination metadata and list of categories.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Total number of categories matching the query", examples=[0, 10, 150], ge=0)
    next: str | None = Field(
        None,
        description="URL to next page of results (null if no next page)",
        examples=["/api/pim/admin/shop/categories/?page=2", None],
    )
    previous: str | None = Field(
        None,
        description="URL to previous page of results (null if no previous page)",
        examples=["/api/pim/admin/shop/categories/?page=1", None],
    )
    results: list[CategoryResponse] = Field(..., description="List of categories in the current page", examples=[[]])


class CategoryDetailResponse(BaseModel):
    """Full category detail response."""

    model_config = ConfigDict(from_attributes=True)

    pk: int = Field(description="Category primary key", examples=[1])
    idx: str = Field(description="Category identifier", examples=["electronics"])
    name: str = Field(description="Category display name (default language)", examples=["Electronics"])
    name_t9n: dict = Field(description="Translated names", examples=[{"en": "Electronics"}])
    desc: str = Field(
        "",
        description="Internal description / instruction. Used to ground AI workflows when matching (feature-set selection, attribute fill). Not shown on the storefront.",
        examples=["Hand tools only; powered tools belong under power-tools."],
    )
    description_t9n: dict = Field(description="Translated descriptions", examples=[{"en": "All electronics"}])
    meta_title_t9n: dict = Field(description="Translated meta titles", examples=[{"en": "Electronics Store"}])
    meta_description_t9n: dict = Field(
        description="Translated meta descriptions", examples=[{"en": "Browse electronics"}]
    )
    canonical_url_t9n: dict = Field(
        default_factory=dict,
        description="Translated canonical URLs",
        examples=[{"en": "https://example.com/electronics"}],
    )
    image_url: str = Field("", description="Category image URL", examples=["https://example.com/category.jpg"])
    og_image_url: str = Field(
        "", description="Open Graph image URL for social sharing", examples=["https://example.com/og.jpg"]
    )
    noindex: bool = Field(False, description="Whether search engines should not index this category", examples=[False])
    nofollow: bool = Field(False, description="Whether search engines should not follow links", examples=[False])
    url_key_t9n: dict = Field(description="Translated URL keys", examples=[{"en": "electronics"}])
    parent_category: int | None = Field(None, description="Parent category PK", examples=[None, 5])
    parent_category_idx: str | None = Field(None, description="Parent category idx", examples=[None, "root"])
    breadcrumb_path: str = Field(description="Full breadcrumb path", examples=["Root > Electronics"])
    tree_deep: int = Field(description="Depth in category tree", examples=[0, 1, 2])
    position: int | None = Field(None, description="Sort position", examples=[10])
    is_active: bool = Field(description="Whether category is active", examples=[True])
    is_in_menu: bool = Field(description="Whether category is in menu", examples=[True])
    product_count: int = Field(description="Number of products in category", examples=[42])
    subcategory_count: int = Field(description="Number of direct subcategories", examples=[3])

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Category service layer for business logic.

This module contains business logic for category operations,
isolated from API and model layers.
"""

from django.db import transaction
from django.db.models import Count, QuerySet
from slugify import slugify

from ..models import Channel, ProductCategory

# Maps API ordering params to actual DB field paths.
ORDERING_MAP: dict[str, str] = {
    "position": "position",
    "-position": "-position",
    "idx": "idx",
    "-idx": "-idx",
    "is_active": "is_active",
    "-is_active": "-is_active",
}


def list_categories(
    channel_idx: str,
    limit: int | None = None,
    search: str | None = None,
    is_active: bool | None = None,
    parent_category_id: int | None = None,
    root_only: bool = False,
    ordering: str | None = None,
) -> QuerySet[ProductCategory]:
    """
    List categories for a given shop with optional filtering.

    Business rules:
    - Returns only categories from the specified shop
    - Supports search by category name
    - Supports filtering by active status
    - Supports filtering by parent category or root categories only
    - Uses select_related for performance optimization
    - Custom ordering supported

    Args:
        channel_idx: Channel identifier (idx field)
        limit: Maximum number of categories to return (optional)
        search: Search term for name filtering (case-insensitive, optional)
        is_active: Filter by active status (optional)
        parent_category_id: Filter by parent category ID (optional)
        root_only: Return only root categories (parent_category is null)
        ordering: Field to order by (optional, default: idx)

    Returns:
        QuerySet of ProductCategory objects

    Raises:
        Channel.DoesNotExist: If channel_idx does not exist
    """
    # Validate channel exists
    channel = Channel.objects.get(idx=channel_idx)

    # Start with base queryset
    queryset = (
        ProductCategory.objects.filter(shop=channel)
        .select_related("shop", "parent_category")
        .annotate(product_count=Count("product_in_category", distinct=True))
    )

    # Apply search filter (name_t9n is JSONField, not a plain CharField)
    if search:
        queryset = queryset.filter(name_t9n__icontains=search)

    # Apply is_active filter
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)

    # Apply parent category filter
    if root_only:
        queryset = queryset.filter(parent_category__isnull=True)
    elif parent_category_id is not None:
        queryset = queryset.filter(parent_category_id=parent_category_id)

    # Apply ordering — default to position so drag-and-drop reorder is reflected
    order_field = ORDERING_MAP.get(ordering, "position") if ordering else "position"
    queryset = queryset.order_by(order_field, "idx")

    # Apply limit if specified
    if limit is not None:
        queryset = queryset[:limit]

    return queryset


def get_category_by_idx(channel_idx: str, idx: str) -> ProductCategory:
    """
    Get a single category by idx for a given shop.

    Business rules:
    - Returns exactly one category matching shop and idx
    - Uses select_related for performance optimization
    - idx lookup is case-sensitive

    Args:
        channel_idx: Channel identifier (idx field)
        idx: Category identifier (idx field)

    Returns:
        ProductCategory object

    Raises:
        Channel.DoesNotExist: If channel_idx does not exist
        ProductCategory.DoesNotExist: If category with idx not found in shop
        ProductCategory.MultipleObjectsReturned: If multiple categories match (data error)
    """
    # Validate channel exists
    channel = Channel.objects.get(idx=channel_idx)

    # Query single category with performance optimization
    category = ProductCategory.objects.filter(shop=channel, idx=idx).select_related("shop", "parent_category").get()

    return category


def get_category_detail(channel_idx: str, idx: str) -> ProductCategory:
    """
    Get a category with annotations for product_count and subcategory_count.

    Raises:
        Channel.DoesNotExist: If channel_idx does not exist
        ProductCategory.DoesNotExist: If category with idx not found in shop
    """
    channel = Channel.objects.get(idx=channel_idx)
    return (
        ProductCategory.objects.filter(shop=channel, idx=idx)
        .select_related("shop", "parent_category")
        .annotate(
            product_count=Count("product_in_category", distinct=True),
            subcategory_count=Count("subcategories", distinct=True),
        )
        .get()
    )


@transaction.atomic
def create_category(
    channel_idx: str,
    idx: str,
    name_t9n: dict,
    desc: str = "",
    description_t9n: dict | None = None,
    meta_title_t9n: dict | None = None,
    meta_description_t9n: dict | None = None,
    canonical_url_t9n: dict | None = None,
    image_url: str = "",
    og_image_url: str = "",
    noindex: bool = False,
    nofollow: bool = False,
    parent_category_idx: str | None = None,
    position: int | None = None,
    is_active: bool = True,
    is_in_menu: bool = True,
) -> ProductCategory:
    """
    Create a new category in a channel.

    Raises:
        Channel.DoesNotExist: If channel_idx does not exist
        ProductCategory.DoesNotExist: If parent_category_idx does not exist in shop
        ValueError: If a category with the given idx already exists in this channel
    """
    channel = Channel.objects.get(idx=channel_idx)

    if ProductCategory.objects.filter(shop=channel, idx=idx).exists():
        raise ValueError(f"Category with idx '{idx}' already exists in channel '{channel_idx}'")

    parent = None
    if parent_category_idx:
        parent = ProductCategory.objects.get(shop=channel, idx=parent_category_idx)

    url_key_t9n = {lang: slugify(str(name)) for lang, name in name_t9n.items() if name}

    category = ProductCategory(
        shop=channel,
        idx=idx,
        name_t9n=name_t9n,
        desc=desc,
        description_t9n=description_t9n or {},
        meta_title_t9n=meta_title_t9n or {},
        meta_description_t9n=meta_description_t9n or {},
        canonical_url_t9n=canonical_url_t9n or {},
        image_url=image_url,
        og_image_url=og_image_url,
        noindex=noindex,
        nofollow=nofollow,
        url_key_t9n=url_key_t9n,
        parent_category=parent,
        position=position,
        is_active=is_active,
        is_in_menu=is_in_menu,
    )
    category.save()
    return category


@transaction.atomic
def update_category(channel_idx: str, idx: str, **fields) -> ProductCategory:
    """
    Update a category. Checks for circular parent references.

    Raises:
        Channel.DoesNotExist: If channel_idx does not exist
        ProductCategory.DoesNotExist: If category or new parent does not exist in shop
        ValueError: If updating parent_category_idx would create a circular reference
    """
    channel = Channel.objects.get(idx=channel_idx)
    category = ProductCategory.objects.get(shop=channel, idx=idx)

    if "parent_category_idx" in fields:
        parent_idx = fields.pop("parent_category_idx")
        if parent_idx is None:
            category.parent_category = None
        else:
            new_parent = ProductCategory.objects.get(shop=channel, idx=parent_idx)
            current = new_parent
            while current is not None:
                if current.pk == category.pk:
                    raise ValueError("Circular category reference")
                current = current.parent_category
            category.parent_category = new_parent

    for field_name in ("name_t9n", "description_t9n", "meta_title_t9n", "meta_description_t9n", "canonical_url_t9n"):
        if field_name in fields and fields[field_name] is not None:
            setattr(category, field_name, fields[field_name])

    for field_name in (
        "desc",
        "image_url",
        "og_image_url",
        "position",
        "is_active",
        "is_in_menu",
        "noindex",
        "nofollow",
    ):
        if field_name in fields and fields[field_name] is not None:
            setattr(category, field_name, fields[field_name])

    if "name_t9n" in fields and fields.get("name_t9n"):
        category.url_key_t9n = {lang: slugify(str(name)) for lang, name in category.name_t9n.items() if name}

    category.save()
    return category


@transaction.atomic
def reorder_categories(channel_idx: str, items: list[dict]) -> int:
    """
    Batch update position and parent_category for multiple categories.

    Saves each category individually so that save() can recalculate tree_deep
    based on the new parent. Checks for circular references on each item.

    Args:
        channel_idx: Channel identifier (idx field)
        items: List of dicts with idx, parent_category_idx, position.

    Returns:
        Number of categories updated.

    Raises:
        Channel.DoesNotExist: If channel_idx does not exist
        ProductCategory.DoesNotExist: If any category or parent does not exist in shop
        ValueError: If any item would create a circular category reference
    """
    channel = Channel.objects.get(idx=channel_idx)
    for item in items:
        category = ProductCategory.objects.get(shop=channel, idx=item["idx"])
        parent_idx = item.get("parent_category_idx")
        if parent_idx is None:
            category.parent_category = None
        else:
            new_parent = ProductCategory.objects.get(shop=channel, idx=parent_idx)
            current = new_parent
            while current is not None:
                if current.pk == category.pk:
                    raise ValueError(f"Circular category reference: '{item['idx']}' would become its own ancestor")
                current = current.parent_category
            category.parent_category = new_parent
        category.position = item["position"]
        category.save()
    return len(items)


@transaction.atomic
def delete_category(channel_idx: str, idx: str) -> dict:
    """
    Delete a category. CASCADE deletes subcategories and ProductInCategory.

    Raises:
        Channel.DoesNotExist: If channel_idx does not exist
        ProductCategory.DoesNotExist: If category with idx not found in shop
    """
    channel = Channel.objects.get(idx=channel_idx)
    category = ProductCategory.objects.get(shop=channel, idx=idx)
    _count, deleted = category.delete()
    return {"deleted": dict(deleted)}

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Service layer for product position management within categories.
"""

from django.db import transaction
from django.db.models import Q

from ..models import Channel, Product, ProductCategory, ProductInCategory


def list_products_in_category(
    channel_idx: str, category_idx: str, search: str | None = None, page: int | None = None, page_size: int = 24
) -> dict:
    """
    List products in a category split into positioned and unpositioned.

    Positioned products (position > 0) are returned in full, ordered by position.
    Unpositioned products (position = 0 or NULL) are paginated and ordered by SKU.

    Raises:
        Channel.DoesNotExist: If channel_idx does not exist
        ProductCategory.DoesNotExist: If category not found in channel
    """
    channel = Channel.objects.get(idx=channel_idx)
    category = ProductCategory.objects.get(shop=channel, idx=category_idx)

    base_qs = ProductInCategory.objects.filter(category=category).select_related(
        "product__real_product", "product__shop"
    )

    if search:
        base_qs = base_qs.filter(product__real_product__sku__icontains=search)

    positioned = list(base_qs.filter(position__gt=0).order_by("position").select_related("product__real_product"))

    unpositioned_qs = base_qs.filter(Q(position=0) | Q(position__isnull=True)).order_by("product__real_product__sku")

    total_unpositioned = unpositioned_qs.count()

    if page is not None and page >= 1:
        offset = (page - 1) * page_size
        unpositioned_items = list(unpositioned_qs[offset : offset + page_size])
    else:
        unpositioned_items = list(unpositioned_qs[:page_size])

    def _get_thumbnail_url(product: Product) -> str | None:
        try:
            thumb = product.thumb_picture
            return getattr(thumb, "url", None) if thumb else None
        except Exception:
            return None

    def _to_dict(pic: ProductInCategory) -> dict:
        product = pic.product
        rp = product.real_product
        return {
            "sku": rp.sku,
            "name": product.name,
            "position": pic.position or 0,
            "is_enabled": product.is_enabled,
            "thumbnail_url": _get_thumbnail_url(product),
        }

    current_page = page if page and page >= 1 else 1
    has_next = (current_page * page_size) < total_unpositioned
    has_previous = current_page > 1

    return {
        "positioned": [_to_dict(p) for p in positioned],
        "unpositioned_count": total_unpositioned,
        "unpositioned": [_to_dict(p) for p in unpositioned_items],
        "unpositioned_next": current_page + 1 if has_next else None,
        "unpositioned_previous": current_page - 1 if has_previous else None,
    }


@transaction.atomic
def reorder_products_in_category(channel_idx: str, category_idx: str, items: list[dict]) -> int:
    """
    Batch update product positions within a category.

    Each item: {"sku": "...", "position": N}
    position=0 unpins, position>0 pins at that position.

    Raises:
        Channel.DoesNotExist: If channel_idx does not exist
        ProductCategory.DoesNotExist: If category not found in channel
        Product.DoesNotExist: If any SKU not found in channel
    """
    channel = Channel.objects.get(idx=channel_idx)
    category = ProductCategory.objects.get(shop=channel, idx=category_idx)

    updated = 0
    for item in items:
        product = Product.objects.get(shop=channel, real_product__sku=item["sku"])
        rows = ProductInCategory.objects.filter(product=product, category=category).update(position=item["position"])
        if rows == 0:
            raise ProductInCategory.DoesNotExist(f"Product '{item['sku']}' is not in category '{category_idx}'")
        updated += rows

    return updated

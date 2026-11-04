# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
ProductLink service layer for business logic.

CRUD operations for product-to-product links (related, crosssell, upsell, etc.).
"""

from django.db import IntegrityError, transaction
from django.db.models import QuerySet

from ..models import Channel, Product, ProductLink, ProductLinkType
from ..settings import SYSTEM_FEATURE_NAME_IDX

# Maps API ordering params to actual DB field paths.
ORDERING_MAP: dict[str, str] = {
    "position": "position",
    "-position": "-position",
}

_EDITABLE_FIELDS = frozenset({"link_type_idx", "position"})


def _is_duplicate(link: ProductLink) -> bool:
    """Another link already joins these products with this type (the model's unique_together)."""
    others = ProductLink.objects.filter(
        product_id=link.product_id, linked_product_id=link.linked_product_id, link_type_id=link.link_type_id
    )
    return others.exclude(pk=link.pk).exists()


def _duplicate_error(sku: str, link: ProductLink) -> ValueError:
    linked_sku = link.linked_product.real_product.sku
    return ValueError(f"Product link already exists: {sku} → {linked_sku} ({link.link_type.idx})")


def _save_unique(sku: str, link: ProductLink) -> None:
    """Save the link; a duplicate, found by the check or by unique_together under a concurrent request, is a ValueError."""
    if _is_duplicate(link):
        raise _duplicate_error(sku, link)
    try:
        with transaction.atomic():
            link.save()
    except IntegrityError:
        raise _duplicate_error(sku, link) from None


def resolve_product_name(product: Product) -> str:
    """Resolve product name from the system 'name' feature attribute."""
    pa = product.products_attributes.filter(feature__idx=SYSTEM_FEATURE_NAME_IDX).first()
    if pa and pa.value_txt:
        return pa.value_txt
    return product.real_product.sku


def list_product_links(
    channel_idx: str, sku: str, link_type_idx: str | None = None, ordering: str | None = None
) -> QuerySet[ProductLink]:
    """
    List product links for a given product.

    Args:
        channel_idx: Channel identifier
        sku: Product SKU
        link_type_idx: Filter by link type idx
        ordering: Field to order by (default: position)

    Raises:
        Channel.DoesNotExist: If channel not found
        Product.DoesNotExist: If product not found
    """
    channel = Channel.objects.get(idx=channel_idx)
    product = Product.objects.select_related("real_product").get(shop=channel, real_product__sku__iexact=sku)

    queryset = ProductLink.objects.filter(product=product).select_related("linked_product__real_product", "link_type")

    if link_type_idx:
        queryset = queryset.filter(link_type__idx=link_type_idx)

    order_field = ORDERING_MAP.get(ordering, "position") if ordering else "position"
    queryset = queryset.order_by(order_field)

    return queryset


def get_product_link(channel_idx: str, sku: str, pk: int) -> ProductLink:
    """
    Get a single product link.

    Raises:
        Channel.DoesNotExist: If channel not found
        Product.DoesNotExist: If product not found
        ProductLink.DoesNotExist: If link not found
    """
    channel = Channel.objects.get(idx=channel_idx)
    product = Product.objects.select_related("real_product").get(shop=channel, real_product__sku__iexact=sku)

    return ProductLink.objects.select_related("linked_product__real_product", "link_type").get(product=product, pk=pk)


@transaction.atomic
def create_product_link(
    channel_idx: str, sku: str, linked_product_sku: str, link_type_idx: str, position: int = 1
) -> ProductLink:
    """
    Create a product link.

    Business rules:
    - Both products must exist in the same channel
    - Self-linking is rejected
    - Duplicate (product, linked_product, link_type) raises ValueError

    Raises:
        Channel.DoesNotExist: If channel not found
        Product.DoesNotExist: If product not found
        ProductLinkType.DoesNotExist: If link type not found
        ValueError: If self-link or duplicate
    """
    channel = Channel.objects.get(idx=channel_idx)
    product = Product.objects.select_related("real_product").get(shop=channel, real_product__sku__iexact=sku)
    linked_product = Product.objects.select_related("real_product").get(
        shop=channel, real_product__sku__iexact=linked_product_sku
    )
    link_type = ProductLinkType.objects.get(idx=link_type_idx)

    if product.pk == linked_product.pk:
        raise ValueError("Cannot link a product to itself")

    link = ProductLink(product=product, linked_product=linked_product, link_type=link_type, position=position)
    _save_unique(sku, link)

    return ProductLink.objects.select_related("linked_product__real_product", "link_type").get(pk=link.pk)


@transaction.atomic
def update_product_link(channel_idx: str, sku: str, pk: int, **fields: object) -> ProductLink:
    """Update a product link.

    Raises:
        Channel.DoesNotExist, Product.DoesNotExist, ProductLink.DoesNotExist, ProductLinkType.DoesNotExist
        ValueError: If a field is not editable, or the new link type duplicates another link between the same products
    """
    invalid = set(fields) - _EDITABLE_FIELDS
    if invalid:
        raise ValueError(f"Fields not editable via update_product_link: {sorted(invalid)}")
    channel = Channel.objects.get(idx=channel_idx)
    product = Product.objects.select_related("real_product").get(shop=channel, real_product__sku__iexact=sku)
    link = ProductLink.objects.get(product=product, pk=pk)

    if "link_type_idx" in fields and fields["link_type_idx"] is not None:
        link.link_type = ProductLinkType.objects.get(idx=fields.pop("link_type_idx"))

    for field, value in fields.items():
        if value is not None:
            setattr(link, field, value)
    _save_unique(sku, link)

    return ProductLink.objects.select_related("linked_product__real_product", "link_type").get(pk=link.pk)


@transaction.atomic
def delete_product_link(channel_idx: str, sku: str, pk: int) -> dict:
    """Delete a product link."""
    channel = Channel.objects.get(idx=channel_idx)
    product = Product.objects.select_related("real_product").get(shop=channel, real_product__sku__iexact=sku)
    link = ProductLink.objects.get(product=product, pk=pk)
    _, deleted_detail = link.delete()
    result = {}
    for key, count in deleted_detail.items():
        simple_name = key.split(".")[-1] if "." in key else key
        result[simple_name] = count
    return result

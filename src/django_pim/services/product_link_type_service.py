# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
ProductLinkType service layer for business logic.

CRUD operations for configurable product link types.
"""

from django.db.models import Q, QuerySet

from .. import settings
from ..models import ProductLinkType

# Maps API ordering params to actual DB field paths.
ORDERING_MAP: dict[str, str] = {
    "position": "position",
    "-position": "-position",
    "idx": "idx",
    "-idx": "-idx",
}


def list_product_link_types(search: str | None = None, ordering: str | None = None) -> QuerySet[ProductLinkType]:
    """
    List product link types with optional filtering.

    Args:
        search: Search term for idx/name filtering (case-insensitive)
        ordering: Field to order by (default: position, idx)
    """
    queryset = ProductLinkType.objects.all()

    if search:
        queryset = queryset.filter(Q(idx__icontains=search) | Q(name_t9n__icontains=search))

    order_field = ORDERING_MAP.get(ordering, "position") if ordering else "position"
    queryset = queryset.order_by(order_field)

    return queryset


def get_product_link_type_by_idx(idx: str) -> ProductLinkType:
    """
    Get a single product link type by idx.

    Raises:
        ProductLinkType.DoesNotExist: If not found
    """
    return ProductLinkType.objects.get(idx=idx)


def resolve_product_link_type_name(link_type: ProductLinkType, language: str | None = None) -> str:
    """Resolve link type name from translation JSON."""
    if language is None:
        language = settings.T9N_DEFAULT_LANG

    langs = [language]
    if language != settings.T9N_DEFAULT_LANG:
        langs.append(settings.T9N_DEFAULT_LANG)

    for lang in langs:
        if lang in link_type.name_t9n:
            name = link_type.name_t9n[lang]
            if name is not None:
                name = str(name).strip()
                if len(name) > 0:
                    return name

    return link_type.idx


def create_product_link_type(idx: str, name_t9n: dict, position: int = 0, desc: str = "") -> ProductLinkType:
    """Create a new product link type."""
    if ProductLinkType.objects.filter(idx=idx).exists():
        raise ValueError(f"ProductLinkType with idx '{idx}' already exists")

    return ProductLinkType.objects.create(idx=idx, name_t9n=name_t9n, position=position, desc=desc)


def update_product_link_type(idx: str, **fields: object) -> ProductLinkType:
    """Update a product link type by idx."""
    link_type = ProductLinkType.objects.get(idx=idx)
    for field, value in fields.items():
        if value is not None:
            setattr(link_type, field, value)
    link_type.save()
    return link_type


def delete_product_link_type(idx: str) -> dict:
    """Delete a product link type by idx."""
    link_type = ProductLinkType.objects.get(idx=idx)
    _, deleted_detail = link_type.delete()
    result = {}
    for key, count in deleted_detail.items():
        simple_name = key.split(".")[-1] if "." in key else key
        result[simple_name] = count
    return result

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
AttributesGroup service layer for business logic.

This module contains business logic for attributes group operations,
isolated from API and model layers.
"""

from django.db.models import Count, Q, QuerySet

from .. import settings
from ..models import AttributesGroup, Channel

# Maps API ordering params to actual DB field paths.
ORDERING_MAP: dict[str, str] = {
    "idx": "idx",
    "-idx": "-idx",
}


def list_attributes_groups(
    channel_idx: str | None = None,
    search: str | None = None,
    ordering: str | None = None,
    limit: int | None = None,
    annotate_counts: bool = True,
) -> QuerySet[AttributesGroup]:
    """
    List attributes groups with optional filtering.

    Args:
        channel_idx: Channel identifier for validation (optional)
        search: Search term for idx/name filtering (case-insensitive, optional)
        ordering: Field to order by (optional, default: idx)
        limit: Maximum number of groups to return (optional)
        annotate_counts: Whether to annotate with attribute counts (default: True)

    Raises:
        Channel.DoesNotExist: If channel_idx provided but does not exist
    """
    # Validate channel exists if provided
    if channel_idx is not None:
        Channel.objects.get(idx=channel_idx)

    # Start with base queryset
    queryset = AttributesGroup.objects.all()

    # Annotate with attribute count for efficient counting
    if annotate_counts:
        queryset = queryset.annotate(attribute_count=Count("attributes"))

    # Apply search filter
    if search:
        queryset = queryset.filter(Q(idx__icontains=search) | Q(name_t9n__icontains=search))

    # Apply ordering
    order_field = ORDERING_MAP.get(ordering, "idx") if ordering else "idx"
    queryset = queryset.order_by(order_field)

    # Apply limit if specified
    if limit is not None:
        queryset = queryset[:limit]

    return queryset


def get_attributes_group_by_idx(idx: str, channel_idx: str | None = None) -> AttributesGroup:
    """
    Get a single attributes group by idx.

    Business rules:
    - Returns exactly one group matching idx
    - Annotates with attribute count
    - Simple lookup by idx

    Args:
        idx: AttributesGroup identifier (idx field)
        channel_idx: Channel identifier for validation (optional)

    Returns:
        AttributesGroup object with attribute_count annotation

    Raises:
        Channel.DoesNotExist: If channel_idx provided but does not exist
        AttributesGroup.DoesNotExist: If group with idx not found
        AttributesGroup.MultipleObjectsReturned: If multiple groups match (data error)
    """
    # Validate channel exists if provided
    if channel_idx is not None:
        Channel.objects.get(idx=channel_idx)

    # Query single group with attribute count
    group = AttributesGroup.objects.annotate(attribute_count=Count("attributes")).get(idx=idx)

    return group


def resolve_attributes_group_name(group: AttributesGroup, language: str | None = None) -> str:
    """
    Resolve attributes group name from translation JSON.

    Business rules:
    - Uses provided language if available
    - Falls back to default language (settings.T9N_DEFAULT_LANG)
    - Falls back to idx if no translation found
    - Same pattern as Feature/Attribute translation

    Args:
        group: AttributesGroup object
        language: Language code (e.g., 'en', 'pl', optional)

    Returns:
        Translated group name
    """
    if language is None:
        language = settings.T9N_DEFAULT_LANG

    # Same logic as Feature/Attribute name resolution
    langs = [language]
    if language != settings.T9N_DEFAULT_LANG:
        langs.append(settings.T9N_DEFAULT_LANG)

    for lang in langs:
        if lang in group.name_t9n:
            name = group.name_t9n[lang]
            if name is not None:
                name = str(name).strip()
                if len(name) > 0:
                    return name

    return group.idx


def create_attributes_group(idx: str, name_t9n: dict, desc: str = "") -> AttributesGroup:
    """Create a new attributes group."""
    if AttributesGroup.objects.filter(idx=idx).exists():
        raise ValueError(f"AttributesGroup with idx '{idx}' already exists")
    group = AttributesGroup(idx=idx, name_t9n=name_t9n, desc=desc)
    group.save()
    return AttributesGroup.objects.annotate(attribute_count=Count("attributes")).get(pk=group.pk)


def update_attributes_group(idx: str, **fields: object) -> AttributesGroup:
    """Update an attributes group by idx."""
    group = AttributesGroup.objects.get(idx=idx)
    for field, value in fields.items():
        if value is not None:
            setattr(group, field, value)
    group.save()
    return AttributesGroup.objects.annotate(attribute_count=Count("attributes")).get(pk=group.pk)


def delete_attributes_group(idx: str) -> dict:
    """Delete an attributes group by idx."""
    group = AttributesGroup.objects.get(idx=idx)
    _, deleted_detail = group.delete()
    result = {}
    for key, count in deleted_detail.items():
        simple_name = key.split(".")[-1] if "." in key else key
        result[simple_name] = count
    return result

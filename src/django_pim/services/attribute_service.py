# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Attribute service layer for business logic.

This module contains business logic for attribute operations,
isolated from API and model layers.
"""

from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet

from .. import settings
from ..models import Attribute, AttributesGroup, Channel, Feature

# Maps API ordering params to actual DB field paths.
ORDERING_MAP: dict[str, str] = {
    "display_order": "display_order",
    "-display_order": "-display_order",
    "idx": "idx",
    "-idx": "-idx",
    "feature__idx": "feature__idx",
    "-feature__idx": "-feature__idx",
}


def list_attributes(
    channel_idx: str | None = None,
    feature_idx: str | None = None,
    group_idx: str | None = None,
    search: str | None = None,
    ordering: str | None = None,
    limit: int | None = None,
) -> QuerySet[Attribute]:
    """
    List attributes with optional filtering.

    Business rules:
    - Returns all attributes by default
    - Can filter by feature and/or group
    - Search by idx (attribute names require translation resolution in view layer)
    - Uses select_related for Feature and AttributesGroup optimization
    - Default ordering by feature__idx, display_order

    Args:
        channel_idx: Channel identifier for validation (optional)
        feature_idx: Filter by feature identifier (optional)
        group_idx: Filter by attributes group identifier (optional)
        search: Search term for idx filtering (case-insensitive, optional)
        ordering: Field to order by (optional, default: feature__idx, display_order)
        limit: Maximum number of attributes to return (optional)

    Returns:
        QuerySet of Attribute objects

    Raises:
        Channel.DoesNotExist: If channel_idx provided but does not exist
        Feature.DoesNotExist: If feature_idx provided but does not exist
        AttributesGroup.DoesNotExist: If group_idx provided but does not exist
    """
    # Validate channel exists if provided
    if channel_idx is not None:
        Channel.objects.get(idx=channel_idx)

    # Start with base queryset with optimization
    queryset = Attribute.objects.select_related("feature", "group")

    # Apply feature filter
    if feature_idx is not None:
        # Validate feature exists
        feature = Feature.objects.get(idx=feature_idx)
        queryset = queryset.filter(feature=feature)

    # Apply group filter
    if group_idx is not None:
        # Validate group exists
        group = AttributesGroup.objects.get(idx=group_idx)
        queryset = queryset.filter(group=group)

    # Apply search filter (search by idx and name_t9n JSON text)
    if search:
        queryset = queryset.filter(Q(idx__icontains=search) | Q(name_t9n__icontains=search))

    # Apply ordering
    if ordering:
        queryset = queryset.order_by(ORDERING_MAP.get(ordering, "display_order"))
    else:
        # Default ordering from model Meta
        queryset = queryset.order_by("feature__idx", "display_order")

    # Apply limit if specified
    if limit is not None:
        queryset = queryset[:limit]

    return queryset


def get_attribute_by_composite_key(feature_idx: str, idx: str, channel_idx: str | None = None) -> Attribute:
    """
    Get a single attribute by composite key (feature, idx).

    Business rules:
    - Attribute has composite unique key (feature, idx)
    - Uses select_related for Feature and AttributesGroup optimization
    - Both feature_idx and idx are required (composite key)

    Args:
        feature_idx: Feature identifier (feature.idx)
        idx: Attribute identifier within feature
        channel_idx: Channel identifier for validation (optional)

    Returns:
        Attribute object with related Feature and AttributesGroup

    Raises:
        Channel.DoesNotExist: If channel_idx provided but does not exist
        Feature.DoesNotExist: If feature_idx does not exist
        Attribute.DoesNotExist: If attribute with composite key not found
        Attribute.MultipleObjectsReturned: If multiple attributes match (data error)
    """
    # Validate channel exists if provided
    if channel_idx is not None:
        Channel.objects.get(idx=channel_idx)

    # Get feature (validates it exists)
    feature = Feature.objects.get(idx=feature_idx)

    # Query single attribute by composite key with optimization
    attribute = Attribute.objects.select_related("feature", "group").get(feature=feature, idx=idx)

    return attribute


def list_attributes_for_feature(
    feature_idx: str, channel_idx: str | None = None, ordering: str | None = None, limit: int | None = None
) -> QuerySet[Attribute]:
    """
    List all attributes for a specific feature.

    Business rules:
    - Returns all attributes belonging to the specified feature
    - Ordered by display_order for consistent presentation
    - Uses select_related for optimization
    - Useful for "get all color options" type queries

    Args:
        feature_idx: Feature identifier (feature.idx)
        channel_idx: Channel identifier for validation (optional)
        ordering: Field to order by (optional, default: display_order)
        limit: Maximum number of attributes to return (optional)

    Returns:
        QuerySet of Attribute objects for the feature

    Raises:
        Channel.DoesNotExist: If channel_idx provided but does not exist
        Feature.DoesNotExist: If feature_idx does not exist
    """
    # Validate channel exists if provided
    if channel_idx is not None:
        Channel.objects.get(idx=channel_idx)

    # Get feature (validates it exists)
    feature = Feature.objects.get(idx=feature_idx)

    # Query attributes for feature with optimization
    queryset = Attribute.objects.filter(feature=feature).select_related("feature", "group")

    # Apply ordering
    order_field = ORDERING_MAP.get(ordering, "display_order") if ordering else "display_order"
    queryset = queryset.order_by(order_field)

    # Apply limit if specified
    if limit is not None:
        queryset = queryset[:limit]

    return queryset


def resolve_attribute_name(attribute: Attribute, language: str | None = None) -> str:
    """
    Resolve attribute name from translation JSON.

    Business rules:
    - Uses provided language if available
    - Falls back to default language (settings.T9N_DEFAULT_LANG)
    - Falls back to idx if no translation found

    Args:
        attribute: Attribute object
        language: Language code (e.g., 'en', 'pl', optional)

    Returns:
        Translated attribute name
    """
    if language is None:
        language = settings.T9N_DEFAULT_LANG

    return attribute.name_lang(language)


def create_attribute(
    feature_idx: str, idx: str, name_t9n: dict, group_idx: str | None = None, display_order: int = 100, desc: str = ""
) -> Attribute:
    """Create a new attribute for a feature."""
    feature = Feature.objects.get(idx=feature_idx)
    group = None
    if group_idx is not None:
        group = AttributesGroup.objects.get(idx=group_idx)
    try:
        attr = Attribute(
            feature=feature, idx=idx, name_t9n=name_t9n, group=group, display_order=display_order, desc=desc
        )
        with transaction.atomic():
            attr.save()
        return attr
    except IntegrityError:
        raise ValueError(f"Attribute '{idx}' already exists for feature '{feature_idx}'") from None


def update_attribute(feature_idx: str, idx: str, **fields: object) -> Attribute:
    """Update an attribute by composite key (feature_idx, idx)."""
    feature = Feature.objects.get(idx=feature_idx)
    attr = Attribute.objects.select_related("feature", "group").get(feature=feature, idx=idx)
    for field, value in fields.items():
        if value is not None:
            if field == "group_idx":
                attr.group = AttributesGroup.objects.get(idx=value)
            else:
                setattr(attr, field, value)
    attr.save()
    return attr


def reorder_attributes(items: list[dict]) -> int:
    """
    Batch update display_order for multiple attributes.

    Args:
        items: List of dicts with feature_idx, idx, display_order.

    Returns:
        Number of attributes updated.

    Raises:
        Attribute.DoesNotExist: If any attribute not found.
    """
    attributes_to_update = []
    for item in items:
        feature = Feature.objects.get(idx=item["feature_idx"])
        attr = Attribute.objects.get(feature=feature, idx=item["idx"])
        attr.display_order = item["display_order"]
        attributes_to_update.append(attr)

    if attributes_to_update:
        Attribute.objects.bulk_update(attributes_to_update, ["display_order"])

    return len(attributes_to_update)


def delete_attribute(feature_idx: str, idx: str) -> dict:
    """Delete an attribute by composite key."""
    feature = Feature.objects.get(idx=feature_idx)
    attr = Attribute.objects.get(feature=feature, idx=idx)
    _, deleted_detail = attr.delete()
    result = {}
    for key, count in deleted_detail.items():
        simple_name = key.split(".")[-1] if "." in key else key
        result[simple_name] = count
    return result

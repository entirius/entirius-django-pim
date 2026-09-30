# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
FeatureSet service layer for business logic.

This module contains business logic for feature set operations,
isolated from API and model layers.
"""

from django.db import IntegrityError, transaction
from django.db.models import Count, Q, QuerySet

from ..models import AttributesGroup, Channel, Feature, FeatureInFeatureSet, FeatureScopeEnum, FeatureSet
from . import gap_rule_service

# Maps API ordering params to actual DB field paths.
ORDERING_MAP: dict[str, str] = {
    "idx": "idx",
    "-idx": "-idx",
    "name": "name",
    "-name": "-name",
    "is_default": "is_default",
    "-is_default": "-is_default",
}

REQUIRED_SOURCE_SYSTEM = "system"
REQUIRED_SOURCE_FEATURE = "feature"
REQUIRED_SOURCE_FEATURE_SET = "feature_set"

FEATURE_IN_SET_ORDERING_MAP: dict[str, str] = {
    "position": "position",
    "-position": "-position",
}


def list_feature_sets(
    channel_idx: str | None = None,
    search: str | None = None,
    is_default: bool | None = None,
    ordering: str | None = None,
    limit: int | None = None,
    annotate_counts: bool = True,
) -> QuerySet[FeatureSet]:
    """
    List feature sets with optional filtering.

    Args:
        channel_idx: Channel identifier for validation (optional)
        search: Search term for idx/name filtering (case-insensitive, optional)
        is_default: Filter by default status (optional)
        ordering: Field to order by (optional, default: idx)
        limit: Maximum number of feature sets to return (optional)
        annotate_counts: Whether to annotate with feature counts (default: True)

    Raises:
        Channel.DoesNotExist: If channel_idx provided but does not exist
    """
    # Validate channel exists if provided
    if channel_idx is not None:
        Channel.objects.get(idx=channel_idx)

    # Start with base queryset
    queryset = FeatureSet.objects.all()

    # Annotate with feature count for efficient counting
    if annotate_counts:
        queryset = queryset.annotate(feature_count=Count("features"))

    # Apply search filter (FeatureSet has plain CharField name)
    if search:
        queryset = queryset.filter(Q(idx__icontains=search) | Q(name__icontains=search))

    # Apply is_default filter
    if is_default is not None:
        queryset = queryset.filter(is_default=is_default)

    # Apply ordering
    order_field = ORDERING_MAP.get(ordering, "idx") if ordering else "idx"
    queryset = queryset.order_by(order_field)

    # Apply limit if specified
    if limit is not None:
        queryset = queryset[:limit]

    return queryset


def get_feature_set_by_idx(idx: str, channel_idx: str | None = None) -> FeatureSet:
    """
    Get a single feature set by idx.

    Business rules:
    - Returns exactly one feature set matching idx
    - Validates shop if channel_idx provided
    - Annotates with feature count
    - idx lookup is case-sensitive

    Args:
        idx: FeatureSet identifier (idx field)
        channel_idx: Channel identifier for validation (optional)

    Returns:
        FeatureSet object with feature_count annotation

    Raises:
        Channel.DoesNotExist: If channel_idx provided but does not exist
        FeatureSet.DoesNotExist: If feature set with idx not found
        FeatureSet.MultipleObjectsReturned: If multiple feature sets match (data error)
    """
    # Validate channel exists if provided
    if channel_idx is not None:
        Channel.objects.get(idx=channel_idx)

    # Query single feature set with feature count
    feature_set = FeatureSet.objects.annotate(feature_count=Count("features")).get(idx=idx)

    return feature_set


def list_features_in_feature_set(
    feature_set_idx: str, channel_idx: str | None = None, ordering: str | None = None, limit: int | None = None
) -> QuerySet[FeatureInFeatureSet]:
    """
    List features within a feature set, ordered by position.

    Business rules:
    - Returns features ordered by position within the set
    - Uses select_related for Feature optimization
    - Default ordering by position (ascending)
    - Channel validation if channel_idx provided

    Args:
        feature_set_idx: FeatureSet identifier (idx field)
        channel_idx: Channel identifier for validation (optional)
        ordering: Field to order by (optional, default: position)
        limit: Maximum number of features to return (optional)

    Returns:
        QuerySet of FeatureInFeatureSet objects with related Feature

    Raises:
        Channel.DoesNotExist: If channel_idx provided but does not exist
        FeatureSet.DoesNotExist: If feature set not found
    """
    # Validate channel exists if provided
    if channel_idx is not None:
        Channel.objects.get(idx=channel_idx)

    # Get the feature set (validates it exists)
    feature_set = FeatureSet.objects.get(idx=feature_set_idx)

    # Query features in set with optimization
    queryset = FeatureInFeatureSet.objects.filter(feature_set=feature_set).select_related("feature", "attributes_group")

    # Apply ordering
    order_field = FEATURE_IN_SET_ORDERING_MAP.get(ordering, "position") if ordering else "position"
    queryset = queryset.order_by(order_field)

    # Apply limit if specified
    if limit is not None:
        queryset = queryset[:limit]

    return queryset


def _enforce_single_default(exclude_pk: int | None = None) -> None:
    """Demote all other feature sets when setting a new default."""
    qs = FeatureSet.objects.filter(is_default=True)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    qs.update(is_default=False)


def create_feature_set(idx: str, name: str = "", desc: str = "", is_default: bool = False) -> FeatureSet:
    """Create a new feature set. Raises ValueError on validation errors."""
    try:
        with transaction.atomic():
            if is_default:
                _enforce_single_default()
            fs = FeatureSet(idx=idx, name=name, desc=desc, is_default=is_default)
            fs.save()
        if is_default:
            # Default identity changed — `feature_set_default` outcomes shift catalogue-wide.
            gap_rule_service.mark_rules_changed()
        return fs
    except IntegrityError:
        raise ValueError(f"Feature set with idx '{idx}' already exists") from None


def update_feature_set(idx: str, **fields: object) -> FeatureSet:
    """Update a feature set by idx. Only provided non-None fields are updated."""
    fs = FeatureSet.objects.get(idx=idx)
    was_default = fs.is_default
    for field, value in fields.items():
        if value is not None:
            setattr(fs, field, value)
    with transaction.atomic():
        if fs.is_default:
            _enforce_single_default(exclude_pk=fs.pk)
        fs.save()
    if fs.is_default != was_default:
        # Default identity changed — `feature_set_default` outcomes shift catalogue-wide,
        # so prompt a recompute (same semantics as the gaps/settings/ skip-default toggle).
        gap_rule_service.mark_rules_changed()
    return FeatureSet.objects.annotate(feature_count=Count("features")).get(pk=fs.pk)


def delete_feature_set(idx: str) -> dict:
    """Delete a feature set. Returns count of deleted objects by model."""
    fs = FeatureSet.objects.get(idx=idx)
    _, deleted_detail = fs.delete()
    result = {}
    for key, count in deleted_detail.items():
        simple_name = key.split(".")[-1] if "." in key else key
        result[simple_name] = count
    return result


def bulk_add_features_to_set(feature_set_idx: str, features: list[dict]) -> list[FeatureInFeatureSet]:
    """Add features to a set.

    Each dict has 'feature_idx' and optional 'position', 'attributes_group_idx' and 'is_required'
    (per-set override; absent or None inherits Feature.is_required).
    """
    fs = FeatureSet.objects.get(idx=feature_set_idx)
    results = []
    for entry in features:
        feature = Feature.objects.get(idx=entry["feature_idx"])
        position = entry.get("position") or 500
        group = None
        if group_idx := entry.get("attributes_group_idx"):
            group = AttributesGroup.objects.get(idx=group_idx)
        fifs = FeatureInFeatureSet(
            feature_set=fs,
            feature=feature,
            position=position,
            attributes_group=group,
            is_required=entry.get("is_required"),
        )
        try:
            with transaction.atomic():
                fifs.save()
        except IntegrityError:
            raise ValueError(f"Feature '{entry['feature_idx']}' already in set '{feature_set_idx}'") from None
        results.append(fifs)
    return results


def reorder_features_in_set(feature_set_idx: str, features: list[dict]) -> int:
    """
    Batch update positions and group assignments for features in a set.

    Args:
        feature_set_idx: FeatureSet identifier.
        features: List of dicts with feature_idx, position, and optional attributes_group_idx.

    Returns:
        Number of entries updated.

    Raises:
        FeatureSet.DoesNotExist: If feature set not found.
        Feature.DoesNotExist: If any feature not found.
        AttributesGroup.DoesNotExist: If any group not found.
    """
    fs = FeatureSet.objects.get(idx=feature_set_idx)
    entries_to_update = []

    for entry in features:
        fifs = FeatureInFeatureSet.objects.get(feature_set=fs, feature__idx=entry["feature_idx"])
        fifs.position = entry["position"]

        if "attributes_group_idx" in entry:
            group_idx = entry["attributes_group_idx"]
            if group_idx is not None:
                fifs.attributes_group = AttributesGroup.objects.get(idx=group_idx)
            else:
                fifs.attributes_group = None

        entries_to_update.append(fifs)

    if entries_to_update:
        FeatureInFeatureSet.objects.bulk_update(entries_to_update, ["position", "attributes_group"])

    return len(entries_to_update)


def bulk_remove_features_from_set(feature_set_idx: str, feature_idxs: list[str]) -> int:
    """Remove features from a set. Returns count of removed entries."""
    fs = FeatureSet.objects.get(idx=feature_set_idx)
    deleted_count, _ = FeatureInFeatureSet.objects.filter(feature_set=fs, feature__idx__in=feature_idxs).delete()
    return deleted_count


def set_feature_required_override(feature_set_idx: str, feature_idx: str, value: bool | None) -> FeatureInFeatureSet:
    """Set the per-set required override on a membership (None = inherit the feature's flag).

    Only touches ``is_required``; position and group stay as they are.

    Raises:
        FeatureSet.DoesNotExist / Feature.DoesNotExist / FeatureInFeatureSet.DoesNotExist
        ValueError: If the feature has SYSTEM scope (system rules are global).
    """
    fs = FeatureSet.objects.get(idx=feature_set_idx)
    feature = Feature.objects.get(idx=feature_idx)
    membership = FeatureInFeatureSet.objects.select_related("feature", "attributes_group").get(
        feature_set=fs, feature=feature
    )
    membership.is_required = value
    membership.validate_override()
    FeatureInFeatureSet.objects.filter(pk=membership.pk).update(is_required=value)
    return membership


def _system_required_features() -> list[Feature]:
    return list(
        Feature.objects.filter(scope=FeatureScopeEnum.SYSTEM, is_required=True).order_by("display_order", "idx")
    )


def get_required_features(feature_set_idx: str) -> list[tuple[Feature, str]]:
    """Features a product of this set must carry, with where the requirement comes from.

    Source is ``"system"`` (SYSTEM-scope feature flagged required; implicit in every set),
    ``"feature_set"`` (explicit override True on the membership) or ``"feature"`` (inherited
    ``Feature.is_required``). System features first, then memberships by position.

    Raises:
        FeatureSet.DoesNotExist: If the feature set does not exist.
    """
    fs = FeatureSet.objects.get(idx=feature_set_idx)
    result = [(feature, REQUIRED_SOURCE_SYSTEM) for feature in _system_required_features()]
    memberships = (
        FeatureInFeatureSet.objects.filter(feature_set=fs)
        .effective_required()
        .exclude(feature__scope=FeatureScopeEnum.SYSTEM)
        .select_related("feature")
        .order_by("position", "feature__idx")
    )
    for membership in memberships:
        source = REQUIRED_SOURCE_FEATURE if membership.is_required is None else REQUIRED_SOURCE_FEATURE_SET
        result.append((membership.feature, source))
    return result


def required_feature_idxs_by_set() -> dict[str, list[str]]:
    """Required feature idxs (sorted) for every feature set, system features included.

    Sets with nothing required map to ``[]``. Two queries regardless of catalogue size.
    """
    system_idxs = [f.idx for f in _system_required_features()]
    by_set: dict[str, set[str]] = {idx: set(system_idxs) for idx in FeatureSet.objects.values_list("idx", flat=True)}
    rows = (
        FeatureInFeatureSet.objects.effective_required()
        .exclude(feature__scope=FeatureScopeEnum.SYSTEM)
        .values_list("feature_set__idx", "feature__idx")
    )
    for set_idx, feature_idx in rows:
        by_set[set_idx].add(feature_idx)
    return {set_idx: sorted(idxs) for set_idx, idxs in sorted(by_set.items())}

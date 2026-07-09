# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Feature service layer for business logic.

This module contains business logic for feature operations,
isolated from API and model layers.
"""

from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet

from .. import settings
from ..models import Channel, Feature, FeatureScopeEnum
from ..schemas.responses.feature import FeatureResponse

# Fields that cannot be changed on SYSTEM-scoped features via API
SYSTEM_PROTECTED_FIELDS = {"scope", "feature_type", "is_required"}

# Maps API ordering params to actual DB field paths.
ORDERING_MAP: dict[str, str] = {
    "display_order": "display_order",
    "-display_order": "-display_order",
    "idx": "idx",
    "-idx": "-idx",
    "scope": "scope",
    "-scope": "-scope",
    "feature_type": "feature_type",
    "-feature_type": "-feature_type",
}


def list_features(
    channel_idx: str | None = None,
    limit: int | None = None,
    search: str | None = None,
    scope: int | None = None,
    feature_type: int | None = None,
    is_filterable: bool | None = None,
    is_searchable: bool | None = None,
    is_visible: bool | None = None,
    ordering: str | None = None,
    include_system: bool = True,
    exclude_feature_set: str | None = None,
) -> QuerySet[Feature]:
    """
    List features with optional filtering.

    Business rules:
    - Returns features scoped to shop's business unit by default (channel context)
    - Global listing returns all scopes; system features excluded only in library context (exclude_feature_set)
    - Includes system features by default (channel context); set include_system=False to hide
    - Supports search by idx (feature names require translation resolution in view layer)
    - Uses display_order for consistent results
    - No select_related needed (Feature has no foreign keys except ManyToMany)

    Args:
        channel_idx: Channel identifier (idx field, optional for admin listing all)
        limit: Maximum number of features to return (optional)
        search: Search term for idx filtering (case-insensitive, optional)
        scope: Filter by scope enum value (1=SYSTEM, 2=GLOBAL, 3=BUSINESS_UNIT)
        feature_type: Filter by feature type enum value (optional)
        is_filterable: Filter by filterable status (optional)
        is_searchable: Filter by searchable status (optional)
        is_visible: Filter by visible status (optional)
        ordering: Field to order by (optional, default: display_order)
        include_system: Include system features in results (default: False)
        exclude_feature_set: FeatureSet idx — exclude features already assigned to this set

    Returns:
        QuerySet of Feature objects

    Raises:
        Channel.DoesNotExist: If channel_idx provided but does not exist
    """
    # Start with base queryset
    queryset = Feature.objects.all()

    # Apply scope filtering
    if channel_idx is not None:
        # Validate channel exists
        channel = Channel.objects.get(idx=channel_idx)

        if scope is not None:
            # Explicit scope filter takes priority
            queryset = queryset.filter(scope=scope)
        elif include_system:
            queryset = queryset.filter(Q(scope=FeatureScopeEnum.BUSINESS_UNIT) | Q(scope=FeatureScopeEnum.SYSTEM))
        else:
            queryset = queryset.filter(scope=FeatureScopeEnum.BUSINESS_UNIT)
    elif scope is not None:
        # Filter by specific scope if provided
        queryset = queryset.filter(scope=scope)
    elif exclude_feature_set is not None:
        # Library context: exclude SYSTEM features (they can't be assigned to sets)
        queryset = queryset.exclude(scope=FeatureScopeEnum.SYSTEM)

    # Apply search filter (search by idx and name_t9n JSON text)
    if search:
        queryset = queryset.filter(Q(idx__icontains=search) | Q(name_t9n__icontains=search))

    # Apply feature_type filter
    if feature_type is not None:
        queryset = queryset.filter(feature_type=feature_type)

    # Apply boolean filters
    if is_filterable is not None:
        queryset = queryset.filter(is_filterable=is_filterable)

    if is_searchable is not None:
        queryset = queryset.filter(is_searchable=is_searchable)

    if is_visible is not None:
        queryset = queryset.filter(is_visible=is_visible)

    # Exclude features already assigned to the given feature set
    if exclude_feature_set is not None:
        queryset = queryset.exclude(feature_in_feature_set__feature_set__idx=exclude_feature_set)

    # Apply ordering
    order_field = ORDERING_MAP.get(ordering, "display_order") if ordering else "display_order"
    queryset = queryset.order_by(order_field)

    # Apply limit if specified
    if limit is not None:
        queryset = queryset[:limit]

    return queryset


def get_feature_by_idx(idx: str, channel_idx: str | None = None) -> Feature:
    """
    Get a single feature by idx.

    Business rules:
    - Returns exactly one feature matching idx
    - Validates shop access if channel_idx provided
    - idx lookup is case-sensitive

    Args:
        idx: Feature identifier (idx field)
        channel_idx: Channel identifier for access validation (optional)

    Returns:
        Feature object

    Raises:
        Channel.DoesNotExist: If channel_idx provided but does not exist
        Feature.DoesNotExist: If feature with idx not found
        Feature.MultipleObjectsReturned: If multiple features match (data error)
    """
    # Validate channel exists if provided
    if channel_idx is not None:
        channel = Channel.objects.get(idx=channel_idx)

    # Query single feature
    feature = Feature.objects.get(idx=idx)

    # Validate scope access if shop context provided
    if channel_idx is not None:
        # Business unit and system features are accessible
        if feature.scope not in [FeatureScopeEnum.BUSINESS_UNIT, FeatureScopeEnum.SYSTEM]:
            raise Feature.DoesNotExist(f"Feature '{idx}' not accessible for shop '{channel_idx}'")

    return feature


def resolve_feature_name(feature: Feature, language: str | None = None) -> str:
    """
    Resolve feature name from translation JSON.

    Business rules:
    - Uses provided language if available
    - Falls back to default language (settings.T9N_DEFAULT_LANG)
    - Falls back to idx if no translation found

    Args:
        feature: Feature object
        language: Language code (e.g., 'en', 'pl', optional)

    Returns:
        Translated feature name
    """
    if language is None:
        language = settings.T9N_DEFAULT_LANG

    return feature.name_lang(language)


def create_feature(
    idx: str,
    name_t9n: dict,
    desc: str = "",
    scope: int = 3,
    feature_type: int = 0,
    frontend_input_type: int = 0,
    filter_type: int = 0,
    display_order: int | None = None,
    is_required: bool = False,
    is_visible: bool = True,
    is_filterable: bool = False,
    is_searchable: bool = True,
    is_comparable: bool = False,
    is_for_customization: bool = False,
    exclude_from_inheritance: bool = False,
    has_visual_asset: bool = False,
    is_seo: bool = False,
) -> Feature:
    """Create a new feature. Raises ValueError on duplicate idx or validation errors."""
    if scope == FeatureScopeEnum.SYSTEM:
        raise ValueError(
            "Cannot create features with SYSTEM scope via API. System features are managed by the import pipeline."
        )
    if scope == FeatureScopeEnum.GLOBAL:
        raise ValueError("GLOBAL scope is deprecated. Use BUSINESS_UNIT (3) instead.")
    try:
        f = Feature(
            idx=idx,
            name_t9n=name_t9n,
            desc=desc,
            scope=scope,
            feature_type=feature_type,
            frontend_input_type=frontend_input_type,
            filter_type=filter_type,
            display_order=display_order,
            is_required=is_required,
            is_visible=is_visible,
            is_filterable=is_filterable,
            is_searchable=is_searchable,
            is_comparable=is_comparable,
            is_for_customization=is_for_customization,
            exclude_from_inheritance=exclude_from_inheritance,
            has_visual_asset=has_visual_asset,
            is_seo=is_seo,
        )
        with transaction.atomic():
            f.save()
        return f
    except IntegrityError:
        raise ValueError(f"Feature with idx '{idx}' already exists") from None


def update_feature(idx: str, **fields: object) -> Feature:
    """Update a feature by idx. Only provided non-None fields are updated."""
    f = Feature.objects.get(idx=idx)

    # Block protected field changes on SYSTEM features
    if f.scope == FeatureScopeEnum.SYSTEM:
        violations = SYSTEM_PROTECTED_FIELDS & set(fields.keys())
        if violations:
            raise ValueError(
                f"Cannot modify {', '.join(sorted(violations))} on system feature '{idx}'. "
                f"System features are managed by the import pipeline."
            )

    # Block changing any feature's scope TO SYSTEM or TO GLOBAL
    if "scope" in fields:
        if fields["scope"] == FeatureScopeEnum.SYSTEM:
            raise ValueError("Cannot set scope to SYSTEM via API.")
        if fields["scope"] == FeatureScopeEnum.GLOBAL:
            raise ValueError("GLOBAL scope is deprecated. Use BUSINESS_UNIT (3) instead.")

    for field, value in fields.items():
        if value is not None:
            setattr(f, field, value)
    f.save()
    return f


def delete_feature(idx: str) -> dict:
    """Delete a feature. Returns count of deleted objects by model."""
    f = Feature.objects.get(idx=idx)
    if f.scope == FeatureScopeEnum.SYSTEM:
        raise ValueError(f"Cannot delete system feature '{idx}'. System features are managed by the import pipeline.")
    _, deleted_detail = f.delete()
    result = {}
    for key, count in deleted_detail.items():
        simple_name = key.split(".")[-1] if "." in key else key
        result[simple_name] = count
    return result


def build_feature_response(feature: Feature, language: str | None = None) -> FeatureResponse:
    """Build a FeatureResponse from a Feature model instance."""
    return FeatureResponse(
        pk=feature.pk,
        idx=feature.idx,
        name=resolve_feature_name(feature, language=language),
        name_t9n=feature.name_t9n or {},
        desc=feature.desc,
        scope=feature.scope,
        scope_name=feature.scope_name,
        feature_type=feature.feature_type,
        feature_type_name=feature.feature_type_name,
        frontend_input_type=feature.frontend_input_type,
        frontend_input_type_name=feature.frontend_input_type_name,
        filter_type=feature.filter_type,
        filter_type_name=feature.filter_type_name,
        display_order=feature.display_order,
        is_required=feature.is_required,
        is_visible=feature.is_visible,
        is_filterable=feature.is_filterable,
        is_searchable=feature.is_searchable,
        is_comparable=feature.is_comparable,
        is_for_customization=feature.is_for_customization,
        exclude_from_inheritance=feature.exclude_from_inheritance,
        has_visual_asset=feature.has_visual_asset,
        is_seo=feature.is_seo,
        is_system=feature.scope == FeatureScopeEnum.SYSTEM,
    )

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Inheritance service for PIM products.

Handles materialization of inherited values from the default channel,
override tracking, copy operations, media inheritance, and cross-channel
product creation.

Three independent inheritance flags per product:
- inherit_attributes: all features EXCEPT name/description/short_description
- inherit_descriptions: name, description, short_description features
- inherit_images: ProductPicture, ProductVideo, ProductFile
"""

from collections import defaultdict

from django.db import transaction
from django.db.models import Q

from ..models import (
    Channel,
    Feature,
    FeatureScopeEnum,
    FeatureSet,
    FeatureTypeEnum,
    Product,
    ProductAttribute,
    ProductFile,
    ProductPicture,
    ProductVideo,
)
from ..models.feature_set import FeatureInFeatureSet
from ..settings import DESCRIPTION_FEATURE_IDXS


def get_default_product_for(product: Product, default_channel: Channel | None = None) -> Product | None:
    """Find the same RealProduct on the default channel.

    Args:
        product: The product to find the default counterpart for.
        default_channel: Pre-resolved default channel (avoids extra query in loops).

    Returns None if the product doesn't exist on the default channel.
    """
    if default_channel is None:
        default_channel = Channel.objects.filter(is_default=True).first()
    if not default_channel:
        return None
    if product.shop_id == default_channel.pk:
        return None  # Product IS on the default channel
    return (
        Product.objects.filter(real_product=product.real_product, shop=default_channel)
        .select_related("real_product", "shop", "feature_set")
        .prefetch_related("products_attributes__feature", "products_attributes__attribute")
        .first()
    )


def _get_feature_intersection(
    source_feature_set: FeatureSet,
    target_feature_set: FeatureSet,
    source_product: Product | None = None,
    target_product: Product | None = None,
) -> set[int]:
    """Get feature PKs present in both feature sets, plus system features on both products.

    System features (scope=SYSTEM) are implicit — they exist as ProductAttributes
    but are not assigned to FeatureInFeatureSet. We include them if both products
    have ProductAttributes for them.
    """
    source_features = set(
        FeatureInFeatureSet.objects.filter(feature_set=source_feature_set).values_list("feature_id", flat=True)
    )
    target_features = set(
        FeatureInFeatureSet.objects.filter(feature_set=target_feature_set).values_list("feature_id", flat=True)
    )
    common = source_features & target_features

    # System features (scope=SYSTEM) are implicit — not tracked in FeatureInFeatureSet —
    # so the set intersection above misses them. Include a system feature only if BOTH
    # products carry it as a ProductAttribute; a narrow target must not inherit a system
    # feature it does not itself have (e.g. description into a name-only feature set).
    if source_product is not None:
        source_system = set(
            ProductAttribute.objects.filter(product=source_product, feature__scope=FeatureScopeEnum.SYSTEM).values_list(
                "feature_id", flat=True
            )
        )
        if target_product is not None:
            target_system = set(
                ProductAttribute.objects.filter(
                    product=target_product, feature__scope=FeatureScopeEnum.SYSTEM
                ).values_list("feature_id", flat=True)
            )
            common |= source_system & target_system
        else:
            common |= source_system

    return common


def _is_t9n_type(feature_type: int) -> bool:
    """Check if a feature type uses translation (t9n) values."""
    return feature_type in (FeatureTypeEnum.VARCHAR255_T9N, FeatureTypeEnum.TEXT_T9N, FeatureTypeEnum.JSON_T9N)


def _is_multiselect_type(feature_type: int) -> bool:
    """Check if a feature type is MULTISELECT."""
    return feature_type == FeatureTypeEnum.MULTISELECT


def _copy_attribute_value(
    source_attr: ProductAttribute, target_attr: ProductAttribute, languages: list[str] | None = None
) -> None:
    """Copy value from source to target attribute.

    For t9n types, copies only specified languages (or all if None).
    For non-t9n types, copies the entire value including the attribute FK.
    """
    feature_type = source_attr.feature.feature_type

    if _is_t9n_type(feature_type):
        source_t9n = source_attr.value_txt_t9n or {}
        target_t9n = target_attr.value_txt_t9n or {}

        if languages is None:
            for lang, value in source_t9n.items():
                target_t9n[lang] = value
        else:
            for lang in languages:
                if lang in source_t9n:
                    target_t9n[lang] = source_t9n[lang]

        target_attr.value_txt_t9n = target_t9n
    else:
        # Copy attribute FK (fixes SELECT/MULTISELECT bug)
        target_attr.attribute = source_attr.attribute
        target_attr.value_bool = source_attr.value_bool
        target_attr.value_decimal = source_attr.value_decimal
        target_attr.value_txt = source_attr.value_txt
        target_attr.value_txt_t9n = source_attr.value_txt_t9n
        target_attr.value_json = source_attr.value_json
        target_attr.value_datetime = source_attr.value_datetime

    target_attr.save()


def _apply_attribute_value(source_attr: ProductAttribute, target_attr: ProductAttribute) -> None:
    """Copy all value fields from source to target in-memory (no save).

    Used by _materialize_features_inner which flushes via bulk_create/bulk_update.
    """
    target_attr.attribute = source_attr.attribute
    target_attr.value_bool = source_attr.value_bool
    target_attr.value_decimal = source_attr.value_decimal
    target_attr.value_txt = source_attr.value_txt
    target_attr.value_txt_t9n = source_attr.value_txt_t9n
    target_attr.value_json = source_attr.value_json
    target_attr.value_datetime = source_attr.value_datetime


def _is_description_feature(feature: Feature) -> bool:
    """Check if a feature is a description feature (name/description/short_description)."""
    return feature.idx in DESCRIPTION_FEATURE_IDXS


_BULK_VALUE_FIELDS = [
    "attribute",
    "value_bool",
    "value_decimal",
    "value_txt",
    "value_txt_t9n",
    "value_json",
    "value_datetime",
    "overridden_langs",
]


def _materialize_features_inner(
    product: Product,
    default_product: Product,
    feature_ids: set[int],
) -> int:
    """Core materialization loop shared by materialize_inherited_values and _materialize_for_features.

    Groups source attributes by feature, respects override tracking, handles MULTISELECT.
    Bulk-fetches target attributes and flushes via bulk_create/bulk_update to avoid N+1.
    Returns count of attributes updated.
    """
    source_attrs_by_feature: dict[int, list[ProductAttribute]] = defaultdict(list)
    for pa in default_product.products_attributes.filter(feature_id__in=feature_ids).select_related(
        "feature", "attribute"
    ):
        source_attrs_by_feature[pa.feature_id].append(pa)

    # Bulk-fetch all target attributes in one query (eliminates per-feature lookup)
    target_attrs_by_feature: dict[int, ProductAttribute] = {}
    for pa in ProductAttribute.objects.filter(product=product, feature_id__in=feature_ids).select_related("feature"):
        target_attrs_by_feature[pa.feature_id] = pa

    to_create: list[ProductAttribute] = []
    to_update: list[ProductAttribute] = []
    updated = 0

    for feature_id, source_attr_list in source_attrs_by_feature.items():
        first_source = source_attr_list[0]
        feature = first_source.feature
        is_description = _is_description_feature(feature)

        if is_description and not product.inherit_descriptions:
            continue
        if not is_description and not product.inherit_attributes:
            continue
        if feature.exclude_from_inheritance:
            continue

        if _is_multiselect_type(feature.feature_type):
            updated += _materialize_multiselect(product, feature_id, source_attr_list)
        else:
            source_attr = first_source
            target_attr = target_attrs_by_feature.get(feature_id)
            is_new = target_attr is None

            if is_new:
                target_attr = ProductAttribute(product=product, feature_id=feature_id, attribute=source_attr.attribute)
                target_attr.overridden_langs = []

            overridden = target_attr.overridden_langs or []

            if _is_t9n_type(source_attr.feature.feature_type):
                source_t9n = source_attr.value_txt_t9n or {}
                target_t9n = target_attr.value_txt_t9n or {}
                for lang, value in source_t9n.items():
                    if lang not in overridden:
                        target_t9n[lang] = value
                target_attr.value_txt_t9n = target_t9n
            else:
                if not overridden:
                    _apply_attribute_value(source_attr, target_attr)

            if is_new:
                to_create.append(target_attr)
            else:
                to_update.append(target_attr)
            updated += 1

    if to_create:
        ProductAttribute.objects.bulk_create(to_create, batch_size=500)
    if to_update:
        ProductAttribute.objects.bulk_update(to_update, fields=_BULK_VALUE_FIELDS, batch_size=500)

    return updated


def _materialize_multiselect(product: Product, feature_id: int, source_attrs: list[ProductAttribute]) -> int:
    """Materialize MULTISELECT values — replace non-overridden target rows."""
    existing = list(ProductAttribute.objects.filter(product=product, feature_id=feature_id).select_related("attribute"))

    has_override = any((row.overridden_langs and row.overridden_langs != []) for row in existing)
    if has_override:
        return 0

    ProductAttribute.objects.filter(product=product, feature_id=feature_id).delete()

    new_rows = [
        ProductAttribute(
            product=product,
            feature_id=feature_id,
            attribute=source_attr.attribute,
            value_bool=source_attr.value_bool,
            value_decimal=source_attr.value_decimal,
            value_txt=source_attr.value_txt,
            value_txt_t9n=source_attr.value_txt_t9n,
            value_json=source_attr.value_json,
            value_datetime=source_attr.value_datetime,
            overridden_langs=[],
        )
        for source_attr in source_attrs
    ]
    ProductAttribute.objects.bulk_create(new_rows)
    return len(new_rows)


@transaction.atomic
def materialize_inherited_values(product: Product, default_channel: Channel | None = None) -> int:
    """Materialize inherited attribute values from default channel.

    Respects the granular flags:
    - inherit_descriptions: name, description, short_description features
    - inherit_attributes: all other features

    Args:
        default_channel: Pre-resolved default channel (avoids extra query in loops).

    Returns count of attributes updated.
    """
    if not product.shop.inheritance_enabled:
        return 0
    if not product.inherit_attributes and not product.inherit_descriptions:
        return 0

    default_product = get_default_product_for(product, default_channel=default_channel)
    if not default_product:
        return 0

    common_features = _get_feature_intersection(
        default_product.feature_set, product.feature_set, source_product=default_product, target_product=product
    )
    if not common_features:
        return 0

    return _materialize_features_inner(product, default_product, common_features)


def _materialize_for_features(product: Product, feature_pks: set[int], default_channel: Channel | None = None) -> int:
    """Materialize inherited values for specific features only."""
    if not product.shop.inheritance_enabled:
        return 0
    if not product.inherit_attributes and not product.inherit_descriptions:
        return 0

    default_product = get_default_product_for(product, default_channel=default_channel)
    if not default_product:
        return 0

    common_features = _get_feature_intersection(
        default_product.feature_set, product.feature_set, source_product=default_product, target_product=product
    )
    target_features = common_features & feature_pks
    if not target_features:
        return 0

    return _materialize_features_inner(product, default_product, target_features)


@transaction.atomic
def materialize_inherited_media(product: Product, default_channel: Channel | None = None) -> int:
    """Materialize inherited media (pictures, videos, files) from default channel.

    Deletes old inherited media, copies fresh from default. Local media untouched.

    Args:
        default_channel: Pre-resolved default channel (avoids extra query in loops).

    Returns count of media items created.
    """
    if not product.inherit_images or not product.shop.inheritance_enabled:
        return 0

    default_product = get_default_product_for(product, default_channel=default_channel)
    if not default_product:
        return 0

    # Delete old inherited media (preserve local)
    ProductPicture.objects.filter(product=product, is_inherited=True).delete()
    ProductVideo.objects.filter(product=product, is_inherited=True).delete()
    ProductFile.objects.filter(product=product, is_inherited=True).delete()

    count = 0

    # Collect local (non-inherited) media to avoid unique constraint violations
    local_picture_keys = set(
        ProductPicture.objects.filter(product=product, is_inherited=False).values_list(
            "picture_id", "picture_role", "language_id", named=False
        )
    )
    local_file_ids = set(
        ProductFile.objects.filter(product=product, is_inherited=False).values_list("file_id", flat=True)
    )

    # Copy pictures (skip if local copy exists)
    for pp in default_product.pictures.all():
        key = (pp.picture_id, pp.picture_role, pp.language_id)
        if key in local_picture_keys:
            continue
        ProductPicture.objects.create(
            product=product,
            picture=pp.picture,
            picture_role=pp.picture_role,
            language=pp.language,
            position=pp.position,
            alt_text_t9n=pp.alt_text_t9n,
            is_inherited=True,
        )
        count += 1

    # Copy videos (skip if local copy with same role+language exists)
    for pv in default_product.videos.all():
        ProductVideo.objects.create(
            product=product,
            video=pv.video,
            video_role=pv.video_role,
            language=pv.language,
            position=pv.position,
            is_inherited=True,
        )
        count += 1

    # Copy files (skip if local copy exists)
    for pf in default_product.products.all():  # ProductFile related_name="products"
        if pf.file_id in local_file_ids:
            continue
        ProductFile.objects.create(product=product, file=pf.file, is_inherited=True)
        count += 1

    return count


@transaction.atomic
def propagate_to_inheriting_products(default_product: Product, updated_feature_idxs: list[str] | None = None) -> int:
    """Propagate default channel values to all inheriting products.

    After updating a product on the default channel:
    - Find all Products with same RealProduct + any inheritance flag True
    - For each, materialize inherited values and/or media

    Args:
        default_product: The product on the default channel that was updated.
        updated_feature_idxs: If provided, only propagate for these features.

    Returns count of products updated.
    """
    inheriting = (
        Product.objects.filter(real_product=default_product.real_product, shop__inheritance_enabled=True)
        .filter(Q(inherit_attributes=True) | Q(inherit_descriptions=True) | Q(inherit_images=True))
        .exclude(shop=default_product.shop)
        .select_related("real_product", "shop", "feature_set")
    )

    # Resolve feature PKs once if filtering by idx
    feature_pks = None
    if updated_feature_idxs:
        feature_pks = set(Feature.objects.filter(idx__in=updated_feature_idxs).values_list("pk", flat=True))

    # Resolve default channel once for the entire loop
    default_channel = Channel.objects.filter(is_default=True).first()

    count = 0
    affected_pks: list[int] = []
    for product in inheriting:
        if product.inherit_attributes or product.inherit_descriptions:
            if feature_pks:
                _materialize_for_features(product, feature_pks, default_channel=default_channel)
            else:
                materialize_inherited_values(product, default_channel=default_channel)
        if product.inherit_images:
            materialize_inherited_media(product, default_channel=default_channel)
        affected_pks.append(product.pk)
        count += 1

    _enqueue_gap_recompute_for_children(affected_pks)
    return count


def propagate_media_to_inheriting(default_product: Product) -> int:
    """Propagate media changes from default channel to inheriting products.

    Called by signal handlers when media changes on the default channel.
    """
    inheriting = (
        Product.objects.filter(
            real_product=default_product.real_product, shop__inheritance_enabled=True, inherit_images=True
        )
        .exclude(shop=default_product.shop)
        .select_related("real_product", "shop")
    )

    default_channel = Channel.objects.filter(is_default=True).first()

    count = 0
    affected_pks: list[int] = []
    for product in inheriting:
        materialize_inherited_media(product, default_channel=default_channel)
        affected_pks.append(product.pk)
        count += 1
    _enqueue_gap_recompute_for_children(affected_pks)
    return count


def _enqueue_gap_recompute_for_children(product_pks: list[int]) -> None:
    """Inheritance materialisation writes children via bulk_create/bulk_update — which do NOT fire
    post_save — so the gap signal handlers never see these writes. Enqueue an explicit recompute so a
    fix on the default channel actually clears the inheriting children's findings (etap-03)."""
    if not product_pks:
        return
    from django_pim.signals.dispatch import enqueue_gap_recompute
    from django_pim.signals.killswitch import is_gaps_enabled

    if not is_gaps_enabled():
        return
    for pk in product_pks:
        enqueue_gap_recompute(pk)


@transaction.atomic
def copy_translations(source_product: Product, target_product: Product, languages: list[str] | None = None) -> int:
    """One-time copy of translations from source to target product.

    Copies values AND marks copied languages as overridden
    (since this is an explicit user action, not ongoing inheritance).

    Raises:
        ValueError: If source and target are on the same channel.

    Returns count of attributes copied.
    """
    if source_product.shop_id == target_product.shop_id:
        raise ValueError("Source and target channels cannot be the same")

    common_features = _get_feature_intersection(
        source_product.feature_set,
        target_product.feature_set,
        source_product=source_product,
        target_product=target_product,
    )
    if not common_features:
        return 0

    # Group source attributes by feature_id (handles MULTISELECT)
    source_attrs_by_feature: dict[int, list[ProductAttribute]] = defaultdict(list)
    for pa in source_product.products_attributes.filter(feature_id__in=common_features).select_related(
        "feature", "attribute"
    ):
        source_attrs_by_feature[pa.feature_id].append(pa)

    copied = 0
    for feature_id, source_attr_list in source_attrs_by_feature.items():
        first_source = source_attr_list[0]

        if _is_multiselect_type(first_source.feature.feature_type):
            # MULTISELECT: copy all rows, mark as overridden
            ProductAttribute.objects.filter(product=target_product, feature_id=feature_id).delete()
            for source_attr in source_attr_list:
                ProductAttribute.objects.create(
                    product=target_product,
                    feature_id=feature_id,
                    attribute=source_attr.attribute,
                    value_bool=source_attr.value_bool,
                    value_decimal=source_attr.value_decimal,
                    value_txt=source_attr.value_txt,
                    value_txt_t9n=source_attr.value_txt_t9n,
                    value_json=source_attr.value_json,
                    value_datetime=source_attr.value_datetime,
                    overridden_langs=["*"],
                )
            copied += 1
            continue

        source_attr = first_source
        target_attr = (
            ProductAttribute.objects.filter(product=target_product, feature_id=feature_id)
            .select_related("feature")
            .first()
        )

        if not target_attr:
            target_attr = ProductAttribute(
                product=target_product, feature_id=feature_id, attribute=source_attr.attribute
            )
            target_attr.overridden_langs = []

        _copy_attribute_value(source_attr, target_attr, languages=languages)

        # Mark copied languages as overridden (explicit user action)
        if _is_t9n_type(source_attr.feature.feature_type):
            overridden = set(target_attr.overridden_langs or [])
            if languages:
                overridden.update(languages)
            else:
                overridden.update((source_attr.value_txt_t9n or {}).keys())
            target_attr.overridden_langs = sorted(overridden)
        else:
            target_attr.overridden_langs = ["*"]  # All overridden for non-t9n

        target_attr.save()
        copied += 1

    return copied


@transaction.atomic
def add_product_to_channel(
    source_product: Product,
    target_channel_idx: str,
    copy_content: bool = False,
    inherit_attributes: bool = False,
    inherit_descriptions: bool = False,
    inherit_images: bool = False,
) -> Product:
    """Create the same product (by SKU) in another channel.

    - Creates Product (reuses RealProduct via get_or_create)
    - If copy_content: copies attribute values
    - If any inherit flag: sets flags + materializes values/media

    Raises:
        Channel.DoesNotExist: If target channel doesn't exist.
        ValueError: If product already exists on target channel.
    """
    target_channel = Channel.objects.get(idx=target_channel_idx)

    if Product.objects.filter(shop=target_channel, real_product=source_product.real_product).exists():
        raise ValueError(f"Product with SKU '{source_product.sku}' already exists in channel '{target_channel_idx}'")

    new_product = Product.objects.create(
        real_product=source_product.real_product,
        shop=target_channel,
        feature_set=source_product.feature_set,
        visibility=source_product.visibility,
        is_enabled=source_product.is_enabled,
        product_class=source_product.product_class,
        inherit_attributes=inherit_attributes,
        inherit_descriptions=inherit_descriptions,
        inherit_images=inherit_images,
    )

    if copy_content:
        copy_translations(source_product, new_product)

    if not copy_content and (inherit_attributes or inherit_descriptions):
        materialize_inherited_values(new_product)

    if inherit_images:
        materialize_inherited_media(new_product)

    return new_product


@transaction.atomic
def toggle_language_override(product: Product, feature_idx: str, language: str, override: bool) -> ProductAttribute:
    """Toggle a language between inherited/overridden for one attribute.

    Args:
        product: The product (must have inheritance enabled)
        feature_idx: Feature identifier
        language: Language ISO code
        override: True = user controls, False = inherit from default

    Raises:
        ValueError: If inheritance not enabled or feature not found.
    """
    is_description = feature_idx in DESCRIPTION_FEATURE_IDXS
    if is_description and not product.inherit_descriptions:
        raise ValueError("Description inheritance is not enabled on this product")
    if not is_description and not product.inherit_attributes:
        raise ValueError("Attribute inheritance is not enabled on this product")

    feature = Feature.objects.get(idx=feature_idx)
    attr = ProductAttribute.objects.filter(product=product, feature=feature).first()

    if not attr:
        raise ValueError(f"Attribute for feature '{feature_idx}' not found on product")

    overridden = set(attr.overridden_langs or [])

    if override:
        overridden.add(language)
    else:
        overridden.discard(language)
        # Re-materialize this language from default
        default_product = get_default_product_for(product)
        if default_product and _is_t9n_type(feature.feature_type):
            default_attr = ProductAttribute.objects.filter(product=default_product, feature=feature).first()
            if default_attr:
                target_t9n = attr.value_txt_t9n or {}
                source_t9n = default_attr.value_txt_t9n or {}
                if language in source_t9n:
                    target_t9n[language] = source_t9n[language]
                    attr.value_txt_t9n = target_t9n

    attr.overridden_langs = sorted(overridden)
    attr.save()
    return attr


@transaction.atomic
def toggle_media_override(
    product: Product,
    picture_id: int | None = None,
    video_id: int | None = None,
    file_id: int | None = None,
    override: bool = True,
) -> None:
    """Toggle a media item between inherited and local (overridden).

    When override=True: marks as local (is_inherited=False)
    When override=False: marks as inherited (is_inherited=True)

    Raises:
        ValueError: If media item not found on product.
    """
    if not product.inherit_images:
        raise ValueError("Image inheritance is not enabled on this product")

    if picture_id is not None:
        pp = ProductPicture.objects.filter(product=product, pk=picture_id).first()
        if not pp:
            raise ValueError(f"Picture {picture_id} not found on product")
        pp.is_inherited = not override
        pp.save(update_fields=["is_inherited"])
    elif video_id is not None:
        pv = ProductVideo.objects.filter(product=product, pk=video_id).first()
        if not pv:
            raise ValueError(f"Video {video_id} not found on product")
        pv.is_inherited = not override
        pv.save(update_fields=["is_inherited"])
    elif file_id is not None:
        pf = ProductFile.objects.filter(product=product, pk=file_id).first()
        if not pf:
            raise ValueError(f"File {file_id} not found on product")
        pf.is_inherited = not override
        pf.save(update_fields=["is_inherited"])
    else:
        raise ValueError("Must specify picture_id, video_id, or file_id")

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Product service layer for business logic.

This module contains business logic for product operations,
isolated from API and model layers.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Exists, OuterRef, Q, QuerySet, Subquery

from ..models import (
    Attribute,
    Channel,
    Feature,
    FeatureScopeEnum,
    FeatureSet,
    FeatureTypeEnum,
    PictureRoleEnum,
    Product,
    ProductAttribute,
    ProductCategory,
    ProductInCategory,
    ProductPicture,
    RealProduct,
)
from ..settings import SYSTEM_FEATURE_NAME_IDX, T9N_DEFAULT_LANG
from .attribute_service import resolve_attribute_name
from .channel_service import get_default_channel
from .feature_service import resolve_feature_name
from .gap_definition_service import validate_severity
from .inheritance_service import get_default_product_for
from .lookup_provider import enqueue_refresh as _enqueue_lookup_refresh
from .lookup_provider import touch_real_product as _touch_real_product
from .lookup_provider import touch_real_products as _touch_real_products

# Maps API ordering params to actual DB field paths.
ORDERING_MAP: dict[str, str] = {
    "sku": "real_product__sku",
    "-sku": "-real_product__sku",
    "visibility": "visibility",
    "-visibility": "-visibility",
    "gap_worst_severity": "gap_worst_severity",
    "-gap_worst_severity": "-gap_worst_severity",
    "gap_count": "gap_count",
    "-gap_count": "-gap_count",
}


def _build_name_search_q(term: str, language_codes: list[str] | None = None) -> Q:
    """Build Q filter for product name via translated attributes.

    Searches across all provided languages (from channel.languages M2M).
    Falls back to T9N_DEFAULT_LANG if no languages given.
    """
    langs = language_codes or [T9N_DEFAULT_LANG]
    name_q = Q()
    for lang in langs:
        name_q |= Q(**{f"products_attributes__value_txt_t9n__{lang}__icontains": term})
    return name_q & Q(products_attributes__feature__idx=SYSTEM_FEATURE_NAME_IDX)


def list_products(
    channel_idx: str,
    limit: int | None = None,
    search: str | None = None,
    is_enabled: bool | None = None,
    ordering: str | None = None,
    visibility: int | None = None,
    product_class: int | None = None,
    category_idx: str | None = None,
    has_media: bool | None = None,
    attribute_filters: dict[str, str] | None = None,
    gap_severity: str | None = None,
) -> QuerySet[Product]:
    """
    List products for a given shop with optional filtering.

    Args:
        channel_idx: Channel identifier (idx field)
        limit: Maximum number of products to return
        search: Search term for name/SKU/EAN filtering
        is_enabled: Filter by enabled status
        ordering: Field to order by (default: real_product__sku)
        visibility: Filter by visibility enum value (1-4)
        product_class: Filter by product class enum value (1-3)
        category_idx: Filter by category idx
        has_media: Filter by presence of MAIN picture
        attribute_filters: Dict of feature_idx -> attribute_idx for filtering by attribute values

    Raises:
        Channel.DoesNotExist: If channel_idx does not exist
    """
    channel = Channel.objects.get(idx=channel_idx)

    # Annotate with main picture path via subquery (eliminates N+1)
    main_picture_subquery = Subquery(
        ProductPicture.objects.filter(product=OuterRef("pk"), picture_role=PictureRoleEnum.MAIN)
        .select_related("picture")
        .values("picture__image")[:1]
    )

    queryset = (
        Product.objects.filter(shop=channel)
        .select_related("real_product", "shop", "feature_set")
        .annotate(_main_picture_path=main_picture_subquery)
    )

    if search:
        lang_codes = list(channel.languages.values_list("iso2", flat=True))
        queryset = queryset.filter(
            _build_name_search_q(search, language_codes=[lc.lower() for lc in lang_codes] if lang_codes else None)
            | Q(real_product__sku__icontains=search)
            | Q(real_product__ean__icontains=search)
        ).distinct()

    if is_enabled is not None:
        queryset = queryset.filter(is_enabled=is_enabled)

    if visibility is not None:
        queryset = queryset.filter(visibility=visibility)

    if product_class is not None:
        queryset = queryset.filter(product_class=product_class)

    if category_idx is not None:
        queryset = queryset.filter(product_in_category__category__idx=category_idx).distinct()

    if has_media is not None:
        has_main = Exists(ProductPicture.objects.filter(product=OuterRef("pk"), picture_role=PictureRoleEnum.MAIN))
        if has_media:
            queryset = queryset.filter(has_main)
        else:
            queryset = queryset.exclude(has_main)

    if attribute_filters:
        for feature_idx, attribute_idx in attribute_filters.items():
            queryset = queryset.filter(
                products_attributes__feature__idx=feature_idx, products_attributes__attribute__idx=attribute_idx
            )
        queryset = queryset.distinct()

    if gap_severity is not None:
        validate_severity(gap_severity)
        queryset = queryset.filter(gap_worst_severity=gap_severity)

    # Sort allowlist: only mapped values reach order_by (never raw user input). Unknown ordering
    # falls back to the default sort — the established contract for this endpoint.
    order_field = ORDERING_MAP.get(ordering, "real_product__sku")
    queryset = queryset.order_by(order_field)

    if limit is not None:
        queryset = queryset[:limit]

    return queryset


def get_product_by_sku(channel_idx: str, sku: str) -> Product:
    """
    Get a single product by SKU for a given shop.

    Business rules:
    - Returns exactly one product matching shop and SKU
    - Uses select_related for performance optimization
    - SKU lookup is case-sensitive

    Args:
        channel_idx: Channel identifier (idx field)
        sku: Product SKU (Stock Keeping Unit)

    Returns:
        Product object

    Raises:
        Channel.DoesNotExist: If channel_idx does not exist
        Product.DoesNotExist: If product with SKU not found in shop
        Product.MultipleObjectsReturned: If multiple products match (data error)
    """
    # Validate channel exists
    channel = Channel.objects.get(idx=channel_idx)

    # Query single product with performance optimization
    product = (
        Product.objects.filter(shop=channel, real_product__sku=sku)
        .select_related("real_product", "shop", "feature_set")
        .get()
    )

    return product


def map_attribute_to_sku(channel_idx: str, feature_idx: str) -> dict[str, str]:
    """Build a ``{attribute value_txt: sku}`` index for one VARCHAR/TEXT feature in a channel.

    One query — for resolving an external reference stored as a product attribute (e.g. a
    cross-system id) back to the PIM SKU. Empty values are skipped; on a value collision the
    last product wins (callers should use it for near-unique refs like external ids).
    """
    rows = (
        ProductAttribute.objects.filter(product__shop__idx=channel_idx, feature__idx=feature_idx)
        .exclude(value_txt="")
        .values_list("value_txt", "product__real_product__sku")
    )
    return {value: sku for value, sku in rows}


def get_product_detail(channel_idx: str, sku: str) -> Product:
    """
    Get a product with all related data for the detail view.

    Uses select_related and prefetch_related for optimal performance.

    Raises:
        Channel.DoesNotExist: If channel_idx does not exist
        Product.DoesNotExist: If product with SKU not found in shop
    """
    channel = Channel.objects.get(idx=channel_idx)
    return (
        Product.objects.filter(shop=channel, real_product__sku=sku)
        .select_related("real_product", "shop", "feature_set")
        .prefetch_related(
            "products_attributes__feature", "products_attributes__attribute", "product_in_category__category"
        )
        .get()
    )


def _has_attribute_value(attr_data: dict, feature_type: int) -> bool:
    """Check if the attribute data carries a value for the given type.

    For SELECT/MULTISELECT, key presence means "process this" (even if null/empty
    — that signals deletion). For other types, an explicit None means "set".
    """
    if feature_type == FeatureTypeEnum.MULTISELECT:
        return "attribute_idxs" in attr_data
    if feature_type == FeatureTypeEnum.SELECT:
        return "attribute_idx" in attr_data
    if feature_type == FeatureTypeEnum.BOOL:
        return attr_data.get("value_bool") is not None
    if feature_type == FeatureTypeEnum.DECIMAL:
        return attr_data.get("value_decimal") is not None
    if feature_type in (FeatureTypeEnum.TEMPERATURE, FeatureTypeEnum.LENGTH, FeatureTypeEnum.MASS):
        return attr_data.get("value_decimal") is not None
    if feature_type in (FeatureTypeEnum.VARCHAR255, FeatureTypeEnum.TEXT):
        return attr_data.get("value_txt") is not None
    if feature_type in (FeatureTypeEnum.VARCHAR255_T9N, FeatureTypeEnum.TEXT_T9N):
        return attr_data.get("value_txt_t9n") is not None
    if feature_type in (FeatureTypeEnum.JSON, FeatureTypeEnum.JSON_T9N):
        return attr_data.get("value_json") is not None
    if feature_type == FeatureTypeEnum.DATETIME:
        return attr_data.get("value_datetime") is not None
    return False


def _set_product_attributes(product: Product, attributes: list[dict]) -> None:
    """Set product attribute values, replacing existing values per feature.

    If the incoming data carries a non-null value, the existing record is
    replaced. If all value fields are null, the attribute is left untouched
    (the CMS sends the full feature set, not just changed features).

    Uses bulk queries to avoid N+1: 1 Feature fetch, 1 Attribute fetch,
    1 bulk delete, 1 bulk_create regardless of attribute count.
    Note: bulk_create skips post_save signals — callers must trigger
    Matrix sync explicitly when needed (see update_product).
    """
    feature_idxs = [a["feature_idx"] for a in attributes]
    features_by_idx = {f.idx: f for f in Feature.objects.filter(idx__in=feature_idxs)}

    active = [
        (attr_data, features_by_idx[attr_data["feature_idx"]])
        for attr_data in attributes
        if attr_data["feature_idx"] in features_by_idx
        and _has_attribute_value(attr_data, features_by_idx[attr_data["feature_idx"]].feature_type)
    ]
    if not active:
        return

    attr_lookups: set[tuple[int, str]] = set()
    for attr_data, feature in active:
        if feature.feature_type == FeatureTypeEnum.MULTISELECT:
            for idx in attr_data.get("attribute_idxs") or []:
                attr_lookups.add((feature.pk, idx))
        elif feature.feature_type == FeatureTypeEnum.SELECT:
            idx = attr_data.get("attribute_idx")
            if idx:
                attr_lookups.add((feature.pk, idx))

    attributes_map: dict[tuple[int, str], Attribute] = {}
    if attr_lookups:
        feature_pks = {fk for fk, _ in attr_lookups}
        attr_idxs = {idx for _, idx in attr_lookups}
        for attr in Attribute.objects.filter(feature_id__in=feature_pks, idx__in=attr_idxs):
            attributes_map[(attr.feature_id, attr.idx)] = attr

    active_features = [feature for _, feature in active]
    ProductAttribute.objects.filter(product=product, feature__in=active_features).delete()

    new_attrs: list[ProductAttribute] = []
    for attr_data, feature in active:
        if feature.feature_type == FeatureTypeEnum.MULTISELECT:
            for attr_idx in attr_data.get("attribute_idxs") or []:
                attribute = attributes_map.get((feature.pk, attr_idx))
                if attribute:
                    new_attrs.append(ProductAttribute(product=product, feature=feature, attribute=attribute))

        elif feature.feature_type == FeatureTypeEnum.SELECT:
            attr_idx = attr_data.get("attribute_idx")
            if attr_idx:
                attribute = attributes_map.get((feature.pk, attr_idx))
                if attribute:
                    new_attrs.append(ProductAttribute(product=product, feature=feature, attribute=attribute))

        else:
            create_kwargs: dict = {"product": product, "feature": feature}
            if feature.feature_type == FeatureTypeEnum.BOOL:
                create_kwargs["value_bool"] = attr_data.get("value_bool")
            elif feature.feature_type == FeatureTypeEnum.DECIMAL:
                create_kwargs["value_decimal"] = Decimal(str(attr_data["value_decimal"]))
            elif feature.feature_type in (FeatureTypeEnum.VARCHAR255, FeatureTypeEnum.TEXT):
                create_kwargs["value_txt"] = attr_data["value_txt"]
            elif feature.feature_type in (FeatureTypeEnum.VARCHAR255_T9N, FeatureTypeEnum.TEXT_T9N):
                create_kwargs["value_txt_t9n"] = attr_data["value_txt_t9n"]
            elif feature.feature_type in (FeatureTypeEnum.JSON, FeatureTypeEnum.JSON_T9N):
                create_kwargs["value_json"] = attr_data["value_json"]
            elif feature.feature_type == FeatureTypeEnum.DATETIME:
                create_kwargs["value_datetime"] = attr_data["value_datetime"]
            new_attrs.append(ProductAttribute(**create_kwargs))

    if new_attrs:
        ProductAttribute.objects.bulk_create(new_attrs)


def _set_product_categories(product: Product, channel: Channel, category_idxs: list[str]) -> None:
    """Set product category assignments (full replace).

    Uses bulk queries: 1 fetch, 1 delete, 1 bulk_create.
    """
    ProductInCategory.objects.filter(product=product).delete()
    categories = {c.idx: c for c in ProductCategory.objects.filter(shop=channel, idx__in=category_idxs)}
    ProductInCategory.objects.bulk_create(
        [ProductInCategory(product=product, category=categories[idx]) for idx in category_idxs if idx in categories]
    )


@transaction.atomic
def create_product(
    channel_idx: str,
    sku: str,
    feature_set_idx: str,
    visibility: int = 4,
    is_enabled: bool = True,
    product_class: int = 1,
    ean: str | None = None,
    weight: str | None = None,
    width: str | None = None,
    height: str | None = None,
    deep: str | None = None,
    kind_of_product: int = 0,
    attributes: list[dict] | None = None,
    category_idxs: list[str] | None = None,
) -> Product:
    """
    Create a new product in a channel.

    Uses get_or_create on RealProduct to handle SKUs shared across channels.

    Raises:
        Channel.DoesNotExist: If channel_idx does not exist
        FeatureSet.DoesNotExist: If feature_set_idx does not exist
        ValueError: If a product with the given SKU already exists in this channel
    """
    channel = Channel.objects.get(idx=channel_idx)
    feature_set = FeatureSet.objects.get(idx=feature_set_idx)

    if Product.objects.filter(shop=channel, real_product__sku=sku).exists():
        raise ValueError(f"Product with SKU '{sku}' already exists in channel '{channel_idx}'")

    real_product, _created = RealProduct.objects.get_or_create(
        sku=sku,
        defaults={
            "ean": ean or "",
            "kind_of_product": kind_of_product,
            "weight": Decimal(weight) if weight else None,
            "width": Decimal(width) if width else None,
            "height": Decimal(height) if height else None,
            "deep": Decimal(deep) if deep else None,
        },
    )

    product = Product.objects.create(
        real_product=real_product,
        shop=channel,
        feature_set=feature_set,
        visibility=visibility,
        is_enabled=is_enabled,
        product_class=product_class,
    )

    if attributes:
        _set_product_attributes(product, attributes)

    if category_idxs:
        _set_product_categories(product, channel, category_idxs)

    return product


def _update_real_product_fields(real_product: RealProduct, fields: dict) -> bool:
    """Apply shared RealProduct fields (weight, EAN, dimensions). Returns True if changed."""
    changed = False
    for field_name in ("ean", "weight", "width", "height", "deep"):
        if field_name not in fields:
            continue
        value = fields[field_name]
        if value is not None and field_name in ("weight", "width", "height", "deep"):
            value = Decimal(str(value))
        setattr(real_product, field_name, value)
        changed = True
    if changed:
        real_product.save()
    return changed


def _update_product_fields(product: Product, fields: dict) -> bool:
    """Apply channel-scoped Product fields (visibility, is_enabled, feature_set). Returns True if changed."""
    changed = False
    if "visibility" in fields and fields["visibility"] is not None:
        product.visibility = fields["visibility"]
        changed = True
    if "is_enabled" in fields and fields["is_enabled"] is not None:
        product.is_enabled = fields["is_enabled"]
        changed = True
    if "feature_set_idx" in fields and fields["feature_set_idx"] is not None:
        product.feature_set = FeatureSet.objects.get(idx=fields["feature_set_idx"])
        changed = True
    if changed:
        product.save()
    return changed


def _apply_inheritance_flags(product: Product, fields: dict) -> bool:
    """Apply inheritance flag changes and materialize. Returns True if changed."""
    changed = False
    for flag_name in ("inherit_attributes", "inherit_descriptions", "inherit_images"):
        if flag_name in fields and fields[flag_name] is not None:
            setattr(product, flag_name, fields[flag_name])
            changed = True
    if not changed:
        return False

    product.save(update_fields=["inherit_attributes", "inherit_descriptions", "inherit_images"])
    from .inheritance_service import materialize_inherited_media, materialize_inherited_values

    if product.inherit_attributes or product.inherit_descriptions:
        materialize_inherited_values(product)
    else:
        ProductAttribute.objects.filter(product=product).update(overridden_langs=[])
    if product.inherit_images:
        materialize_inherited_media(product)
    return True


def _propagate_if_default(product: Product, fields: dict) -> None:
    """Propagate attribute changes to inheriting products if on default channel."""
    if not product.shop.is_default or "attributes" not in fields or not fields["attributes"]:
        return

    from .inheritance_service import propagate_to_inheriting_products

    updated_feature_idxs = [a["feature_idx"] for a in fields["attributes"]]
    has_inheriting = (
        Product.objects.filter(real_product=product.real_product, shop__inheritance_enabled=True)
        .filter(Q(inherit_attributes=True) | Q(inherit_descriptions=True))
        .exclude(shop=product.shop)
        .exists()
    )
    if has_inheriting:
        propagate_to_inheriting_products(product, updated_feature_idxs)


@transaction.atomic
def update_product(channel_idx: str, sku: str, **fields) -> Product:
    """
    Update a product. RealProduct fields (weight, EAN, etc.) are shared across channels.

    Raises:
        Channel.DoesNotExist: If channel_idx does not exist
        Product.DoesNotExist: If product with SKU not found in shop
    """
    channel = Channel.objects.get(idx=channel_idx)
    product = (
        Product.objects.filter(shop=channel, real_product__sku=sku).select_related("real_product", "feature_set").get()
    )

    rp_changed = _update_real_product_fields(product.real_product, fields)
    product_changed = _update_product_fields(product, fields)
    inheritance_changed = _apply_inheritance_flags(product, fields)

    attributes_changed = "attributes" in fields and fields["attributes"] is not None
    categories_changed = "category_idxs" in fields and fields["category_idxs"] is not None

    if attributes_changed:
        _set_product_attributes(product, fields["attributes"])
    if categories_changed:
        _set_product_categories(product, channel, fields["category_idxs"])

    # bulk_create/delete skip per-row signals; fire post_save once for Matrix sync.
    if (attributes_changed or categories_changed) and not (product_changed or rp_changed or inheritance_changed):
        from django.db.models.signals import post_save

        post_save.send(sender=Product, instance=product, created=False, raw=False, update_fields=None)

    if attributes_changed or product_changed or inheritance_changed:
        # Display data the fingerprint reads changed on Product/ProductAttribute, which do not
        # touch RealProduct.updated_at — keep `lookup_backfill --since` honest.
        _touch_real_product(product.real_product_id)

    _propagate_if_default(product, fields)
    return product


@transaction.atomic
def delete_product(channel_idx: str, sku: str) -> dict:
    """
    Delete a Product (channel-scoped). Does NOT delete the RealProduct.

    Raises:
        Channel.DoesNotExist: If channel_idx does not exist
        Product.DoesNotExist: If product with SKU not found in shop
    """
    channel = Channel.objects.get(idx=channel_idx)
    product = Product.objects.filter(shop=channel, real_product__sku=sku).get()
    real_product_id = product.real_product_id
    _count, deleted = product.delete()
    _touch_real_product(real_product_id)
    return {"deleted": dict(deleted)}


@transaction.atomic
def bulk_update_products(
    channel_idx: str,
    skus: list[str],
    is_enabled: bool | None = None,
    visibility: int | None = None,
    category_idxs_add: list[str] | None = None,
    category_idxs_remove: list[str] | None = None,
) -> dict:
    """
    Bulk update multiple products in a single transaction.

    Raises:
        Channel.DoesNotExist: If channel_idx does not exist
    """
    channel = Channel.objects.get(idx=channel_idx)
    products = Product.objects.filter(shop=channel, real_product__sku__in=skus)

    update_fields: dict = {}
    if is_enabled is not None:
        update_fields["is_enabled"] = is_enabled
    if visibility is not None:
        update_fields["visibility"] = visibility

    if is_enabled is not None:
        # Read the skus BEFORE the update: `products` is a lazy queryset, and the rows still match
        # it afterwards, but resolving it first keeps the refs stable if that ever stops holding.
        toggled_skus = list(products.values_list("real_product__sku", flat=True))
    updated = products.update(**update_fields) if update_fields else products.count()

    if is_enabled is not None:
        # `queryset.update()` fires no signals, and `is_enabled` decides which channel Product a
        # lookup fingerprint describes (`lookup_provider._display_product`) — so nudge lookup by
        # hand. `visibility` needs no nudge: nothing in the fingerprint reads it.
        _touch_real_products(toggled_skus)
        _enqueue_lookup_refresh(toggled_skus)

    if category_idxs_add:
        categories = list(ProductCategory.objects.filter(shop=channel, idx__in=category_idxs_add))
        product_list = list(products)
        existing = set(
            ProductInCategory.objects.filter(product__in=product_list, category__in=categories).values_list(
                "product_id", "category_id"
            )
        )
        ProductInCategory.objects.bulk_create(
            [
                ProductInCategory(product=p, category=c)
                for p in product_list
                for c in categories
                if (p.pk, c.pk) not in existing
            ],
            ignore_conflicts=True,
        )

    if category_idxs_remove:
        categories = ProductCategory.objects.filter(shop=channel, idx__in=category_idxs_remove)
        ProductInCategory.objects.filter(product__in=products, category__in=categories).delete()

    return {"updated": updated}


# -- Detail response data assembly (moved from view layer) --

SYSTEM_T9N_KEYS = (
    "description",
    "short_description",
    "url_key",
    "meta_title",
    "meta_description",
    "subname",
    "subname2",
    "canonical_url",
)
SYSTEM_PLAIN_KEYS = ("og_image",)


def _build_attribute_data(pa, language: str | None, default_attrs: dict) -> dict:
    """Build a single attribute dict for detail response."""
    feature = pa.feature
    inherited_values = None
    if pa.feature_id in default_attrs:
        default_pa = default_attrs[pa.feature_id]
        if default_pa.value_txt_t9n:
            inherited_values = default_pa.value_txt_t9n

    return {
        "feature_idx": feature.idx,
        "feature_name": resolve_feature_name(feature, language=language),
        "feature_type": feature.feature_type,
        "feature_type_name": feature.feature_type_name,
        "value_bool": pa.value_bool,
        "value_decimal": str(pa.value_decimal) if pa.value_decimal is not None else None,
        "value_txt": pa.value_txt,
        "value_txt_t9n": pa.value_txt_t9n if pa.value_txt_t9n else None,
        "value_json": pa.value_json if pa.value_json else None,
        "value_datetime": str(pa.value_datetime) if pa.value_datetime else None,
        "attribute_idx": pa.attribute.idx if pa.attribute else None,
        "attribute_name": resolve_attribute_name(pa.attribute, language=language) if pa.attribute else None,
        "overridden_langs": pa.overridden_langs or [],
        "inherited_values": inherited_values,
    }


def _build_system_values(product_attrs: list) -> tuple[dict, dict]:
    """Extract system feature t9n and plain values from pre-fetched attributes."""
    system_t9n = {k: {} for k in SYSTEM_T9N_KEYS}
    system_plain = dict.fromkeys(SYSTEM_PLAIN_KEYS, "")
    for pa in product_attrs:
        if pa.feature.scope != FeatureScopeEnum.SYSTEM:
            continue
        if pa.feature.idx in system_t9n:
            system_t9n[pa.feature.idx] = pa.value_txt_t9n or {}
        elif pa.feature.idx in system_plain:
            system_plain[pa.feature.idx] = pa.value_txt or ""
    return system_t9n, system_plain


def _build_categories(product: Product) -> list[dict]:
    """Build category brief dicts for product detail response."""
    return [
        {
            "pk": pic.category.pk,
            "idx": pic.category.idx,
            "name": pic.category.name,
            "breadcrumb_path": pic.category.breadcrumb_path,
        }
        for pic in product.product_in_category.all()
    ]


def _build_channel_presence(product: Product) -> tuple[list[str], int]:
    """Return (present_in_channels, inheriting_channels_count)."""
    present_in_channels = list(
        Product.objects.filter(real_product=product.real_product).values_list("shop__idx", flat=True)
    )
    inheriting_channels_count = 0
    if product.shop.is_default:
        inheriting_channels_count = (
            Product.objects.filter(real_product=product.real_product)
            .exclude(shop=product.shop)
            .filter(Q(inherit_attributes=True) | Q(inherit_descriptions=True) | Q(inherit_images=True))
            .count()
        )
    return present_in_channels, inheriting_channels_count


def build_product_detail_data(product: Product, language: str | None = None) -> dict:
    """Assemble all data needed for ProductDetailResponse.

    Returns a flat dict ready to unpack into ProductDetailResponse(**data).
    """
    has_any_inheritance = product.inherit_attributes or product.inherit_descriptions or product.inherit_images

    default_channel = None
    default_attrs: dict = {}
    if has_any_inheritance:
        default_channel = get_default_channel()
        default_product = get_default_product_for(product)
        if default_product:
            default_attrs = {pa.feature_id: pa for pa in default_product.products_attributes.all()}

    # Single fetch of product attributes — reused for attributes list and system values
    product_attrs = list(product.products_attributes.all())

    attributes = [_build_attribute_data(pa, language, default_attrs) for pa in product_attrs]
    system_t9n, system_plain = _build_system_values(product_attrs)
    categories = _build_categories(product)
    present_in_channels, inheriting_channels_count = _build_channel_presence(product)

    rp = product.real_product
    return {
        "pk": product.pk,
        "sku": product.sku,
        "name": product.name,
        "name_t9n": product.name_t9n_json or {},
        "description_t9n": system_t9n["description"],
        "short_description_t9n": system_t9n["short_description"],
        "url_key_t9n": system_t9n["url_key"],
        "meta_title_t9n": system_t9n["meta_title"],
        "meta_description_t9n": system_t9n["meta_description"],
        "canonical_url_t9n": system_t9n["canonical_url"],
        "og_image": system_plain["og_image"],
        "subname_t9n": system_t9n["subname"],
        "subname2_t9n": system_t9n["subname2"],
        "visibility": product.visibility,
        "visibility_name": product.visibility_name,
        "is_enabled": product.is_enabled,
        "product_class": product.product_class,
        "product_class_name": product.product_class_name,
        "feature_set_idx": product.feature_set.idx,
        "weight": str(rp.weight) if rp.weight is not None else None,
        "width": str(rp.width) if rp.width is not None else None,
        "height": str(rp.height) if rp.height is not None else None,
        "deep": str(rp.deep) if rp.deep is not None else None,
        "ean": rp.ean or None,
        "kind_of_product": rp.kind_of_product,
        "inherit_attributes": product.inherit_attributes,
        "inherit_descriptions": product.inherit_descriptions,
        "inherit_images": product.inherit_images,
        "default_channel_idx": default_channel.idx if default_channel else None,
        "present_in_channels": present_in_channels,
        "inheriting_channels_count": inheriting_channels_count,
        "categories": categories,
        "attributes": attributes,
        "gap_worst_severity": product.gap_worst_severity,
        "gap_count": product.gap_count,
        "gap_evaluated_at": product.gap_evaluated_at.isoformat() if product.gap_evaluated_at else None,
    }

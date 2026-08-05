# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django_pim.models import ProductAttribute, ProductBundle
from django_pim.models.product_bundle.bundle_link import BundleLink
from django_pim.settings import (
    SYSTEM_FEATURE_MAX_LIMIT_BUNDLE_IDX,
    SYSTEM_FEATURE_MIN_LIMIT_BUNDLE_IDX,
    SYSTEM_FEATURE_OPTIONAL_TITLE_IDX,
    T9N_DEFAULT_LANG,
)


def get_bundle_subproducts(channel_idx: str, sku_list: list[str]) -> dict[str, dict[str, dict]]:
    """Bulk-fetch BundleLink rows for the given bundle SKUs on one channel.

    Returns:
        {bundle_sku: {sub_sku: {"quantity", "is_required", "is_default", "can_change_quantity"}}}

    Bundles without BundleLinks are absent from the result.

    SKUs live on the shared RealProduct, so `channel_idx` is required: without it
    BundleLinks from every channel selling the same SKU merge under one key.
    """
    links = (
        BundleLink.objects.filter(product_bundle__shop__idx=channel_idx, product_bundle__real_product__sku__in=sku_list)
        .select_related("product_bundle__real_product", "subproduct__real_product")
        .values(
            "product_bundle__real_product__sku",
            "subproduct__real_product__sku",
            "quantity",
            "is_required",
            "is_default",
            "can_change_quantity",
        )
    )
    result: dict[str, dict[str, dict]] = {}
    for link in links:
        bundle_sku = link["product_bundle__real_product__sku"]
        sub_sku = link["subproduct__real_product__sku"]
        result.setdefault(bundle_sku, {})[sub_sku] = {
            "quantity": link["quantity"],
            "is_required": link["is_required"],
            "is_default": link["is_default"],
            "can_change_quantity": link["can_change_quantity"],
        }
    return result


def get_bundle_limits(channel_idx: str, sku_list: list[str]) -> dict[str, dict]:
    """Read min_limit_bundle / max_limit_bundle attributes for bundle SKUs on one channel.

    Returns:
        {bundle_sku: {"min"?: int, "max"?: int}}

    Bundles without any limit set are absent from the result. Callers can use
    `bool(limits.get(sku))` as the legacy/ranged discriminator.

    For worker-scale loads (thousands of bundles in one pass), prefer
    `bulk_get_bundle_limits` — it issues a single ORM query.
    """
    limits: dict[str, dict] = {}
    for bundle in ProductBundle.objects.filter(shop__idx=channel_idx, real_product__sku__in=sku_list):
        sku = bundle.real_product.sku
        entry: dict = {}
        raw_max = bundle.get_max_limit_bundle()
        if raw_max is not None:
            try:
                entry["max"] = int(raw_max)
            except (ValueError, TypeError):
                pass
        raw_min = bundle.get_min_limit_bundle()
        if raw_min is not None:
            try:
                entry["min"] = int(raw_min)
            except (ValueError, TypeError):
                pass
        if entry:
            limits[sku] = entry
    return limits


def bulk_get_bundle_limits(channel_idx: str, sku_list: list[str]) -> dict[str, dict]:
    """Single-query variant of get_bundle_limits — for worker-scale loads.

    Joins through ProductAttribute → Feature so we read both limit attributes
    for many bundles in one round-trip. Same return shape as get_bundle_limits.

    `product__productbundle__isnull=False` is the multi-table-inheritance join that
    keeps this a drop-in for get_bundle_limits: without it a simple or configurable
    product carrying a stale limit attribute would be returned here but not there.
    """
    if not sku_list:
        return {}
    limit_idxs = [SYSTEM_FEATURE_MAX_LIMIT_BUNDLE_IDX, SYSTEM_FEATURE_MIN_LIMIT_BUNDLE_IDX]
    qs = ProductAttribute.objects.filter(
        product__shop__idx=channel_idx,
        product__real_product__sku__in=sku_list,
        product__productbundle__isnull=False,
        feature__idx__in=limit_idxs,
    ).select_related("feature", "product__real_product")
    result: dict[str, dict] = {}
    for pa in qs:
        sku = pa.product.real_product.sku
        feature_idx = pa.feature.idx
        value = pa.get_value()
        if value is None:
            continue
        try:
            value_int = int(value)
        except (ValueError, TypeError):
            continue
        entry = result.setdefault(sku, {})
        if feature_idx == SYSTEM_FEATURE_MAX_LIMIT_BUNDLE_IDX:
            entry["max"] = value_int
        elif feature_idx == SYSTEM_FEATURE_MIN_LIMIT_BUNDLE_IDX:
            entry["min"] = value_int
    return result


def get_option_titles(channel_idx: str, sub_sku_list: list[str], language: str) -> dict[str, str]:
    """Read the per-product `option_titles` VARCHAR255_T9N attribute on one channel.

    The attribute lives on each sub-product (not on the bundle) and stores
    a translated title used when the product appears as a bundle option.
    Values are read from `value_txt_t9n` with `T9N_DEFAULT_LANG` fallback.

    Returns:
        {sub_sku: title}

    Sub-SKUs without an attribute or a usable translation are absent.

    Scoped by `channel_idx`: the attribute is per-channel Product data keyed here by
    the shared RealProduct SKU, so without it one channel's title overwrites another's.
    """
    if not sub_sku_list:
        return {}
    qs = ProductAttribute.objects.filter(
        product__shop__idx=channel_idx,
        product__real_product__sku__in=sub_sku_list,
        feature__idx=SYSTEM_FEATURE_OPTIONAL_TITLE_IDX,
    ).select_related("product__real_product")
    result: dict[str, str] = {}
    for pa in qs:
        t9n = pa.value_txt_t9n
        if not isinstance(t9n, dict):
            continue
        for lang in (language, T9N_DEFAULT_LANG):
            raw = t9n.get(lang)
            if raw is None:
                continue
            title = str(raw).strip()
            if title:
                result[pa.product.real_product.sku] = title
                break
    return result


def get_default_subproducts(subproducts_data: dict) -> dict:
    """Pure rule: which subproducts are auto-selected by default in a ranged bundle.

    Default selection = BundleLinks where `is_required=True OR is_default=True`.
    Each contributes its `BundleLink.quantity`.

    Returns {sub_sku: quantity_per_one_bundle}. Empty dict if no defaults exist.

    Caller is responsible for the "is this bundle ranged?" gate — this function
    does not look at limits. Callers that need to extend the rule with a customer
    selection (cart flow) layer their own logic on top.
    """
    return {
        sub_sku: meta["quantity"]
        for sub_sku, meta in subproducts_data.items()
        if meta["is_required"] or meta["is_default"]
    }

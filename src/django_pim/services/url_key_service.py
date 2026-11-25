# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The product ``url_key`` (SYSTEM, translated): generation and per-channel uniqueness.

The storefront opens a product page by ``url_key``, so a product without one is listed by search and then "not
found". A missing key is ``slug(name)-slug(sku)`` per language that has a name; a key already taken in the
channel for that language gets ``-2``, ``-3``, … A key that is given is never touched, except to resolve a
collision after a copy between channels (``dedupe_url_keys``).
"""

from idx_normalizator import normalize_url_key

from ..models import Channel, Feature, FeatureScopeEnum, Product, ProductAttribute
from ..settings import SYSTEM_FEATURE_NAME_IDX, SYSTEM_FEATURE_URL_KEY_IDX
from .attribute_plan import AttributePlan, PlannedFeature

URL_KEY_MAX_LENGTH = 200
_SUFFIX_ROOM = 8  # "-" and up to seven digits of the collision counter


def _is_blank(value: object) -> bool:
    return value is None or not str(value).strip()


def build_url_key(name: str, sku: str) -> str:
    """``slug(name)-slug(sku)``, at most ``URL_KEY_MAX_LENGTH - _SUFFIX_ROOM`` long (room for the suffix)."""
    sku_part = normalize_url_key(sku)
    room = URL_KEY_MAX_LENGTH - _SUFFIX_ROOM - len(sku_part) - 1
    name_part = normalize_url_key(name)[: max(room, 0)].strip("-")
    return "-".join(part for part in (name_part, sku_part) if part)


def _url_key_feature() -> Feature | None:
    return Feature.objects.filter(idx=SYSTEM_FEATURE_URL_KEY_IDX, scope=FeatureScopeEnum.SYSTEM).first()


def _is_taken(channel: Channel, lang: str, key: str, exclude_pk: int | None) -> bool:
    rows = ProductAttribute.objects.filter(
        product__shop=channel,
        feature__idx=SYSTEM_FEATURE_URL_KEY_IDX,
        feature__scope=FeatureScopeEnum.SYSTEM,
        value_txt_t9n__contains={lang: key},
    )
    if exclude_pk is not None:
        rows = rows.exclude(product_id=exclude_pk)
    return rows.exists()


def unique_url_key(channel: Channel, lang: str, base: str, exclude_pk: int | None = None) -> str:
    """``base``, or ``base-2``, ``base-3``… the first one no other product of the channel has for ``lang``."""
    candidate, counter = base, 1
    while _is_taken(channel, lang, candidate, exclude_pk):
        counter += 1
        candidate = f"{base}-{counter}"
    return candidate


def missing_url_keys(
    channel: Channel, sku: str, names: dict, existing: dict, exclude_pk: int | None = None
) -> dict[str, str]:
    """``{lang: key}`` for every language that has a name and no url_key yet."""
    return {
        lang: unique_url_key(channel, lang, build_url_key(str(name), sku), exclude_pk)
        for lang, name in names.items()
        if not _is_blank(name) and _is_blank(existing.get(lang))
    }


def add_generated_url_key(plan: AttributePlan, channel: Channel, sku: str) -> None:
    """Create flow: complete the planned ``url_key`` row from the planned ``name`` row (no DB write)."""
    feature = _url_key_feature()
    names = _planned_t9n(plan, SYSTEM_FEATURE_NAME_IDX)
    if feature is None or not names:
        return
    existing = _planned_t9n(plan, SYSTEM_FEATURE_URL_KEY_IDX)
    generated = missing_url_keys(channel, sku, names, existing)
    if not generated:
        return
    row = {"feature": feature, "value_txt_t9n": {**existing, **generated}}
    plan.planned = [p for p in plan.planned if p.feature.idx != SYSTEM_FEATURE_URL_KEY_IDX]
    plan.planned.append(PlannedFeature(feature, [row]))


def _planned_t9n(plan: AttributePlan, feature_idx: str) -> dict:
    for planned in plan.planned:
        if planned.feature.idx == feature_idx and planned.rows:
            return dict(planned.rows[0].get("value_txt_t9n") or {})
    return {}


def fill_missing_url_key(product: Product, *, apply: bool = True) -> dict[str, str]:
    """Stored product: generate the url_key of every language that has a name and no key.

    Returns the ``{lang: key}`` it set (or would set, with ``apply=False``). Never overwrites a given key.
    """
    feature = _url_key_feature()
    name_row = ProductAttribute.objects.filter(product=product, feature__idx=SYSTEM_FEATURE_NAME_IDX).first()
    if feature is None or name_row is None:
        return {}
    key_row = ProductAttribute.objects.filter(product=product, feature=feature).first()
    existing = dict(key_row.value_txt_t9n or {}) if key_row else {}
    generated = missing_url_keys(product.shop, product.sku, name_row.value_txt_t9n or {}, existing, product.pk)
    if generated and apply:
        key_row = key_row or ProductAttribute(product=product, feature=feature)
        key_row.value_txt_t9n = {**existing, **generated}
        key_row.save()
    return generated


def dedupe_url_keys(product: Product) -> dict[str, str]:
    """After a copy into a channel: give every url_key another product of the channel already has a suffix."""
    key_row = ProductAttribute.objects.filter(
        product=product, feature__idx=SYSTEM_FEATURE_URL_KEY_IDX, feature__scope=FeatureScopeEnum.SYSTEM
    ).first()
    if key_row is None:
        return {}
    keys = dict(key_row.value_txt_t9n or {})
    changed = {
        lang: unique_url_key(product.shop, lang, key, product.pk)
        for lang, key in keys.items()
        if not _is_blank(key) and _is_taken(product.shop, lang, key, product.pk)
    }
    if changed:
        key_row.value_txt_t9n = {**keys, **changed}
        key_row.save()
    return changed


def copy_missing_url_keys(source: Product, target: Product) -> dict[str, str]:
    """Add-to-channel: give ``target`` the source's url_key of every language it has none for, then dedupe.

    Same row shape as ``copy_translations`` makes (copied languages marked overridden). Runs for every
    add-to-channel path, so a product added without ``copy_content`` is not left without a page.
    """
    source_row = ProductAttribute.objects.filter(
        product=source, feature__idx=SYSTEM_FEATURE_URL_KEY_IDX, feature__scope=FeatureScopeEnum.SYSTEM
    ).first()
    if source_row is None:
        return {}
    target_row = ProductAttribute.objects.filter(product=target, feature=source_row.feature).first()
    existing = dict(target_row.value_txt_t9n or {}) if target_row else {}
    copied = {
        lang: key
        for lang, key in (source_row.value_txt_t9n or {}).items()
        if not _is_blank(key) and _is_blank(existing.get(lang))
    }
    if copied:
        target_row = target_row or ProductAttribute(product=target, feature=source_row.feature)
        target_row.value_txt_t9n = {**existing, **copied}
        target_row.overridden_langs = sorted(set(target_row.overridden_langs or []) | set(copied))
        target_row.save()
    dedupe_url_keys(target)
    return copied

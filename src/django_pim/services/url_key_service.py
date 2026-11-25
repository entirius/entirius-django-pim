# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The product ``url_key`` (SYSTEM, translated): generation and per-channel uniqueness.

The storefront opens a product page by ``url_key`` (matrix matches it exactly and has no unique constraint), so a
product without one is "not found" and a duplicate silently opens the wrong product. Rules:

- A missing key is ``slug(name)-slug(sku)`` per language that has a name (``add_generated_url_key``,
  ``fill_missing_url_key``); a key taken in the channel for that language gets ``-2``, ``-3``, …
- A key a user gives that another product of the channel already has is refused (``InvalidRequestError``).
- A key that arrives by copy or inheritance (derived) is suffixed instead, and kept overridden so the next
  propagation does not turn it back into a duplicate (``dedupe_url_keys``, ``settle_inherited_url_keys``).
- Every check-then-write runs under ``lock_url_keys``: one channel at a time, until the transaction ends.
- Existing keys are never rewritten (live URLs); ``find_duplicate_url_keys`` only lists duplicates.
"""

from collections import defaultdict

from django.db import connection, transaction
from django.db.models import QuerySet
from idx_normalizator import normalize_url_key

from ..exceptions import InvalidRequestError
from ..models import Channel, Feature, FeatureScopeEnum, Product, ProductAttribute
from ..settings import SYSTEM_FEATURE_NAME_IDX, SYSTEM_FEATURE_URL_KEY_IDX
from .attribute_plan import AttributePlan, PlannedFeature

URL_KEY_MAX_LENGTH = 200
_SUFFIX_ROOM = 8  # "-" and up to seven digits of the collision counter
URL_KEY_LOCK_NAMESPACE = 1970170475  # first int4 of the advisory lock; the second one is the channel pk


def _is_blank(value: object) -> bool:
    return value is None or not str(value).strip()


def lock_url_keys(channel: Channel) -> None:
    """Serialize url_key writes of one channel until the surrounding transaction ends (call inside ``atomic``)."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [URL_KEY_LOCK_NAMESPACE, channel.pk])


def build_url_key(name: str, sku: str) -> str:
    """``slug(name)-slug(sku)``, at most ``URL_KEY_MAX_LENGTH - _SUFFIX_ROOM`` long (room for the suffix)."""
    sku_part = normalize_url_key(sku)
    room = URL_KEY_MAX_LENGTH - _SUFFIX_ROOM - len(sku_part) - 1
    name_part = normalize_url_key(name)[: max(room, 0)].strip("-")
    return "-".join(part for part in (name_part, sku_part) if part)


def _url_key_feature() -> Feature | None:
    return Feature.objects.filter(idx=SYSTEM_FEATURE_URL_KEY_IDX, scope=FeatureScopeEnum.SYSTEM).first()


def _taken_rows(channel: Channel, lang: str, key: str, exclude_pk: int | None) -> QuerySet:
    """Rows of every product of the channel (disabled and not visible ones too) that has ``key`` for ``lang``."""
    rows = ProductAttribute.objects.filter(
        product__shop=channel,
        feature__idx=SYSTEM_FEATURE_URL_KEY_IDX,
        feature__scope=FeatureScopeEnum.SYSTEM,
        value_txt_t9n__contains={lang: key},
    )
    return rows if exclude_pk is None else rows.exclude(product_id=exclude_pk)


def _is_taken(channel: Channel, lang: str, key: str, exclude_pk: int | None, reserved: set | None = None) -> bool:
    if reserved is not None and (channel.pk, lang, key) in reserved:
        return True
    return _taken_rows(channel, lang, key, exclude_pk).exists()


def _suffixed(base: str, counter: int) -> str:
    suffix = f"-{counter}"
    return f"{base[: URL_KEY_MAX_LENGTH - len(suffix)].rstrip('-')}{suffix}"


def unique_url_key(
    channel: Channel, lang: str, base: str, *, exclude_pk: int | None = None, reserved: set | None = None
) -> str:
    """``base``, or ``base-2``, ``base-3``… (never longer than the limit) that nobody in the channel has for ``lang``.

    ``reserved`` holds ``(channel pk, lang, key)`` of keys chosen but not written yet (dry-run); the pick is added.
    """
    candidate, counter = base, 1
    while _is_taken(channel, lang, candidate, exclude_pk, reserved):
        counter += 1
        candidate = _suffixed(base, counter)
    if reserved is not None:
        reserved.add((channel.pk, lang, candidate))
    return candidate


def refuse_taken_url_keys(channel: Channel, keys: dict, exclude_pk: int | None = None) -> None:
    """A key a user gave must be free: name the language and the SKU that has it, or pass."""
    for lang, key in sorted(keys.items()):
        if _is_blank(key):
            continue
        clash = _taken_rows(channel, lang, key, exclude_pk).select_related("product__real_product").first()
        if clash is not None:
            raise InvalidRequestError(
                f"url_key '{key}' ({lang}) is already used by product '{clash.product.sku}' in channel '{channel.idx}'"
            )


def missing_url_keys(
    channel: Channel,
    sku: str,
    names: dict,
    existing: dict,
    *,
    exclude_pk: int | None = None,
    reserved: set | None = None,
) -> dict[str, str]:
    """``{lang: key}`` for every language that has a name and no url_key yet."""
    return {
        lang: unique_url_key(channel, lang, build_url_key(str(name), sku), exclude_pk=exclude_pk, reserved=reserved)
        for lang, name in names.items()
        if not _is_blank(name) and _is_blank(existing.get(lang))
    }


def _planned_t9n(plan: AttributePlan, feature_idx: str) -> dict:
    for planned in plan.planned:
        if planned.feature.idx == feature_idx and planned.rows:
            return dict(planned.rows[0].get("value_txt_t9n") or {})
    return {}


def add_generated_url_key(plan: AttributePlan, channel: Channel, sku: str) -> None:
    """Create flow (inside ``atomic``): refuse a given key that is taken, complete the rest from the names."""
    feature = _url_key_feature()
    names = _planned_t9n(plan, SYSTEM_FEATURE_NAME_IDX)
    existing = _planned_t9n(plan, SYSTEM_FEATURE_URL_KEY_IDX)
    if feature is None or not (names or existing):
        return
    lock_url_keys(channel)
    refuse_taken_url_keys(channel, existing)
    generated = missing_url_keys(channel, sku, names, existing)
    if generated:
        row = {"feature": feature, "value_txt_t9n": {**existing, **generated}}
        plan.planned = [p for p in plan.planned if p.feature.idx != SYSTEM_FEATURE_URL_KEY_IDX]
        plan.planned.append(PlannedFeature(feature, [row]))


def guard_changed_url_keys(plan: AttributePlan, product: Product) -> None:
    """Update flow (inside ``atomic``): a planned url_key that differs from the stored one must be free.

    Unchanged languages are not checked (the CMS sends the whole feature set; an old duplicate must not block an
    unrelated edit). The name is never used here: a name change does not move a live URL.
    """
    sent = _planned_t9n(plan, SYSTEM_FEATURE_URL_KEY_IDX)
    if not sent:
        return
    lock_url_keys(product.shop)
    stored = _stored_url_keys(product)
    changed = {lang: key for lang, key in sent.items() if stored.get(lang) != key}
    refuse_taken_url_keys(product.shop, changed, exclude_pk=product.pk)


def _stored_url_keys(product: Product) -> dict:
    row = ProductAttribute.objects.filter(
        product=product, feature__idx=SYSTEM_FEATURE_URL_KEY_IDX, feature__scope=FeatureScopeEnum.SYSTEM
    ).first()
    return dict(row.value_txt_t9n or {}) if row else {}


def _fill_missing(product: Product, apply: bool, reserved: set | None) -> dict[str, str]:
    feature = _url_key_feature()
    name_row = ProductAttribute.objects.filter(product=product, feature__idx=SYSTEM_FEATURE_NAME_IDX).first()
    if feature is None or name_row is None:
        return {}
    key_row = ProductAttribute.objects.filter(product=product, feature=feature).first()
    existing = dict(key_row.value_txt_t9n or {}) if key_row else {}
    names = name_row.value_txt_t9n or {}
    generated = missing_url_keys(product.shop, product.sku, names, existing, exclude_pk=product.pk, reserved=reserved)
    if generated and apply:
        key_row = key_row or ProductAttribute(product=product, feature=feature)
        key_row.value_txt_t9n = {**existing, **generated}
        key_row.save()
    return generated


def fill_missing_url_key(product: Product, *, apply: bool = True, reserved: set | None = None) -> dict[str, str]:
    """Stored product: generate the url_key of every language that has a name and no key.

    Returns the ``{lang: key}`` it set (or would set, with ``apply=False``). Never overwrites a given key.
    """
    if not apply:
        return _fill_missing(product, False, reserved)
    with transaction.atomic():
        lock_url_keys(product.shop)
        return _fill_missing(product, True, reserved)


def _url_key_row(product: Product) -> ProductAttribute | None:
    return ProductAttribute.objects.filter(
        product=product, feature__idx=SYSTEM_FEATURE_URL_KEY_IDX, feature__scope=FeatureScopeEnum.SYSTEM
    ).first()


def dedupe_url_keys(product: Product) -> dict[str, str]:
    """After a copy into a channel (inside ``atomic``): suffix every url_key another product of the channel has."""
    key_row = _url_key_row(product)
    if key_row is None:
        return {}
    lock_url_keys(product.shop)
    keys = dict(key_row.value_txt_t9n or {})
    changed = {
        lang: unique_url_key(product.shop, lang, key, exclude_pk=product.pk)
        for lang, key in keys.items()
        if not _is_blank(key) and _is_taken(product.shop, lang, key, product.pk)
    }
    if changed:
        key_row.value_txt_t9n = {**keys, **changed}
        key_row.save()
    return changed


def settle_inherited_url_keys(product: Product, row: ProductAttribute, langs: list[str]) -> None:
    """Propagation (unsaved ``row``, inside ``atomic``): a derived key that collides is suffixed and kept overridden."""
    lock_url_keys(product.shop)
    keys = row.value_txt_t9n or {}
    overridden = set(row.overridden_langs or [])
    for lang in langs:
        key = keys.get(lang)
        if _is_blank(key) or not _is_taken(product.shop, lang, key, product.pk):
            continue
        keys[lang] = unique_url_key(product.shop, lang, key, exclude_pk=product.pk)
        overridden.add(lang)
    row.overridden_langs = sorted(overridden)


def copy_missing_url_keys(source: Product, target: Product) -> dict[str, str]:
    """Add-to-channel (inside ``atomic``): give ``target`` the source's url_key of every language it has none for.

    Same row shape as ``copy_translations`` makes (copied languages marked overridden); a key taken in the target
    channel is suffixed. Runs for every add-to-channel path, so a product added without ``copy_content`` is not
    left without a page.
    """
    source_row = _url_key_row(source)
    if source_row is None:
        return {}
    lock_url_keys(target.shop)
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


def find_duplicate_url_keys(channel_idx: str | None = None) -> list[tuple[str, str, str, list[str]]]:
    """Read-only: ``(channel idx, lang, key, [skus])`` for every key two or more products of a channel share."""
    rows = ProductAttribute.objects.filter(
        feature__idx=SYSTEM_FEATURE_URL_KEY_IDX, feature__scope=FeatureScopeEnum.SYSTEM
    )
    if channel_idx:
        rows = rows.filter(product__shop__idx=channel_idx)
    owners: dict[tuple[str, str, str], dict[str, None]] = defaultdict(dict)
    values = rows.order_by("product__shop__idx", "product__real_product__sku").values_list(
        "product__shop__idx", "product__real_product__sku", "value_txt_t9n"
    )
    for channel, sku, t9n in values.iterator():
        for lang, key in (t9n or {}).items():
            if not _is_blank(key):
                owners[(channel, lang, key)][sku] = None
    return [(c, lang, key, list(skus)) for (c, lang, key), skus in sorted(owners.items()) if len(skus) > 1]

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""PIM provider for the django-lookup module (kind `pim_product`).

Lookup never imports PIM: it loads this module lazily by dotted path from
`settings.LOOKUP_PROVIDERS = {"pim_product": "django_pim.services.lookup_provider"}` and calls the
module-level functions below (duck-typed against `django_lookup.providers.base`). Like the
enrichment adapter, this file imports nothing from the consuming module — `ProviderItem` /
`BasicData` are mirrored here so PIM keeps zero dependency on an optional module. Field names are
the contract; `django_lookup.providers.base` is authoritative for them.

One item per `RealProduct`; `ref` = SKU. A RealProduct is a per-channel projection hub, so display
data (name, brand, mpn, picture) comes from ONE product — the first enabled one, else the first by
id — while identifiers and physicals come from the RealProduct itself.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime

from ..models import Feature, PictureRoleEnum, Product, RealProduct
from ..settings import SYSTEM_FEATURE_BRAND_IDX, SYSTEM_FEATURE_NAME_IDX, T9N_DEFAULT_LANG

# MPN has no system feature in PIM — installations model it as a business-unit feature `mpn`.
MPN_FEATURE_IDX = "mpn"
DETAIL_URL = "/api/pim/v2/admin/{channel_idx}/products/{sku}/"
# Shared with `lookup_bridge` (the call side of the same boundary) — declared once.
PHYSICAL_ATTRS = ("weight", "width", "height", "deep")
# Everything a provider item needs, in one round trip per batch (no query inside the loop).
_RELATED = ("products__shop__default_language", "products__products_attributes__feature", "products__pictures__picture")


@dataclass(frozen=True)
class ProviderItem:
    """Mirror of django_lookup.providers.base.ProviderItem (duplicated to avoid the import)."""

    ref: str
    gtin: str | None = None
    brand: str | None = None
    mpn: str | None = None
    name_by_lang: dict[str, str] = field(default_factory=dict)
    attrs: dict = field(default_factory=dict)
    image_path_or_url: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class BasicData:
    """Mirror of django_lookup.providers.base.BasicData."""

    ref: str
    name: str
    brand: str = ""
    gtin: str = ""
    mpn: str = ""
    image_url: str = ""


def iter_items(since: datetime | None = None) -> Iterator[ProviderItem]:
    """Stream every RealProduct (optionally only those touched since `since`).

    `since` compares `RealProduct.updated_at`, which only the RealProduct's own fields (sku, ean,
    physicals) bump. Display data lives on Product / ProductAttribute / ProductPicture, whose writes
    leave that column alone — an incremental run is therefore an identifier-level catch-up, not a
    full drift repair. The freshness signals cover those writes row by row; use a full backfill
    (no `since`) after any period when the `lookup` queue was not running.
    """
    queryset = RealProduct.objects.all()
    if since is not None:
        queryset = queryset.filter(updated_at__gte=since)
    for real_product in queryset.prefetch_related(*_RELATED).order_by("id").iterator(chunk_size=500):
        yield _item(real_product)


def get_item(ref: str) -> ProviderItem:
    return _item(_require(ref))


def basic(ref: str) -> BasicData:
    """Display data for one lookup hit. `basics` is the form lookup actually uses (see it)."""
    return _basic(_require(ref))


def detail_url(ref: str) -> str:
    """Admin API deep link. Channel-scoped in PIM — the display product decides which channel."""
    product = _display_product(_require(ref))
    if product is None:
        raise LookupError(f"RealProduct sku={ref!r} has no product in any channel")
    return DETAIL_URL.format(channel_idx=product.shop.idx, sku=ref)


def basics(refs: list[str]) -> dict[str, BasicData]:
    """Batch form of `basic` — the optional protocol extension in `django_lookup.providers.base`.

    Without it lookup falls back to the singular pair, and one hit then costs two full `_require`
    round trips (~8 queries each, `_RELATED` has three prefetch legs) — ~80 queries for the create
    hook's five candidates. Here the whole hit list is one round trip.

    Contract: refs the provider no longer serves are OMITTED, never raised — the batch form has no
    per-ref slot to carry "gone".
    """
    return {real_product.sku: _basic(real_product) for real_product in _fetch(refs)}


def detail_urls(refs: list[str]) -> dict[str, str]:
    """Batch form of `detail_url`. A RealProduct with no product in any channel has no deep link,
    so it is omitted — the batch equivalent of the `LookupError` the singular call raises."""
    urls = {}
    for real_product in _fetch(refs):
        if product := _display_product(real_product):
            urls[real_product.sku] = DETAIL_URL.format(channel_idx=product.shop.idx, sku=real_product.sku)
    return urls


def signal_specs() -> list[dict]:
    """Senders django-lookup connects so a fingerprint follows the catalog (see its signals.py)."""
    return [
        {"model": "django_pim.RealProduct", "signal": "post_save", "ref": lambda rp: rp.sku},
        {"model": "django_pim.Product", "signal": "post_save", "ref": _ref_for_product},
        {"model": "django_pim.ProductAttribute", "signal": "post_save", "ref": _ref_for_attribute},
        {"model": "django_pim.ProductPicture", "signal": "post_save", "ref": _ref_for_picture},
        {"model": "django_pim.ProductPicture", "signal": "post_delete", "ref": _ref_for_picture},
    ]


FINGERPRINTED_FEATURE_IDXS = frozenset({SYSTEM_FEATURE_NAME_IDX, SYSTEM_FEATURE_BRAND_IDX, MPN_FEATURE_IDX})
# Cached 60s (house pattern: signals/killswitch.py) so a non-fingerprinted attribute save — the
# common case on every enrichment apply / admin edit / per-row importer — costs zero extra queries
# instead of a `Feature` fetch per row.
FINGERPRINTED_FEATURE_IDS_CACHE_KEY = "pim:lookup:fingerprinted_feature_ids"


def _ref_for_product(product) -> str | None:
    """Attribute writes that go through `bulk_create` never fire a per-row `post_save`.

    `product_service.update_product` compensates by sending one `post_save` for the Product itself —
    without this sender a rename (name / brand / mpn) would leave the fingerprint stale forever.
    No `watch`: the compensating send skips `pre_save`, so a watched-column snapshot would be stale
    from the product's own save and swallow exactly the event this exists to catch.
    """
    return product.real_product.sku if product.real_product_id else None


def _fingerprinted_feature_ids() -> frozenset[int]:
    """`Feature.id` for `FINGERPRINTED_FEATURE_IDXS`, cached 60s.

    `attribute.feature_id` is a plain column (always resolved, no query); checking it against this
    set avoids the `attribute.feature.idx` fetch that a fresh-from-DB `ProductAttribute` would
    otherwise trigger on every save.
    """
    from django.core.cache import cache

    cached = cache.get(FINGERPRINTED_FEATURE_IDS_CACHE_KEY)
    if cached is not None:
        return cached
    ids = frozenset(Feature.objects.filter(idx__in=FINGERPRINTED_FEATURE_IDXS).values_list("id", flat=True))
    cache.set(FINGERPRINTED_FEATURE_IDS_CACHE_KEY, ids, 60)
    return ids


def _ref_for_attribute(attribute) -> str | None:
    if attribute.feature_id not in _fingerprinted_feature_ids():
        return None
    return attribute.product.real_product.sku


def _ref_for_picture(product_picture) -> str | None:
    if product_picture.picture_role != PictureRoleEnum.MAIN:
        return None
    return product_picture.product.real_product.sku


def _require(ref: str) -> RealProduct:
    real_product = RealProduct.objects.filter(sku=ref).prefetch_related(*_RELATED).first()
    if real_product is None:
        raise LookupError(f"no RealProduct with sku={ref!r}")
    return real_product


def _fetch(refs: list[str]) -> list[RealProduct]:
    """One prefetch round trip for a whole hit list; unknown refs simply do not come back."""
    return list(RealProduct.objects.filter(sku__in=refs).prefetch_related(*_RELATED))


def _basic(real_product: RealProduct) -> BasicData:
    """Display data for a hit — the name in the display product's own channel language.

    The same language `brand` / `mpn` are read in (`_attribute_value`): a hit shown in a Polish
    channel must not pair a Polish brand with an English name.
    """
    product = _display_product(real_product)
    names = _names(product)
    language = _default_language(product) if product is not None else T9N_DEFAULT_LANG
    return BasicData(
        ref=real_product.sku,
        name=names.get(language) or names.get(T9N_DEFAULT_LANG) or next(iter(names.values()), ""),
        brand=_attribute_value(product, SYSTEM_FEATURE_BRAND_IDX) or "",
        gtin=real_product.ean or "",
        mpn=_attribute_value(product, MPN_FEATURE_IDX) or "",
        image_url=_main_picture_url(product),
    )


def _item(real_product: RealProduct) -> ProviderItem:
    product = _display_product(real_product)
    return ProviderItem(
        ref=real_product.sku,
        gtin=real_product.ean,
        brand=_attribute_value(product, SYSTEM_FEATURE_BRAND_IDX),
        mpn=_attribute_value(product, MPN_FEATURE_IDX),
        name_by_lang=_names(product),
        attrs={name: getattr(real_product, name) for name in PHYSICAL_ATTRS},
        image_path_or_url=_main_picture_path(product),
        updated_at=real_product.updated_at,
    )


def _display_product(real_product: RealProduct) -> Product | None:
    """First enabled product, else the first one — prefetched, so this sorts in Python."""
    products = sorted(real_product.products.all(), key=lambda p: (not p.is_enabled, p.id))
    return products[0] if products else None


def _names(product: Product | None) -> dict[str, str]:
    """Every language the `name` system feature carries (decision #2: tokens from all languages).

    A non-t9n `name` feature (plain VARCHAR255/TEXT — `product_link_service.resolve_product_name`
    reads exactly that shape) keys its single value under the channel's default language. The query
    side (`lookup_bridge._attribute_text`) reads both shapes, so the fingerprint must too, or such
    an installation can never be matched by name.
    """
    attribute = _attribute(product, SYSTEM_FEATURE_NAME_IDX)
    if attribute is None:
        return {}
    if isinstance(attribute.value_txt_t9n, dict):
        return {lang: str(value).strip() for lang, value in attribute.value_txt_t9n.items() if value}
    if value := (attribute.value_txt or "").strip():
        return {_default_language(product): value}
    return {}


def _attribute(product: Product | None, feature_idx: str):
    """`Feature.idx` is globally unique, so the scope (system vs business unit) never disambiguates."""
    if product is None:
        return None
    for attribute in product.products_attributes.all():  # prefetched — no query per feature
        if attribute.feature.idx == feature_idx:
            return attribute
    return None


def _attribute_value(product: Product | None, feature_idx: str) -> str | None:
    attribute = _attribute(product, feature_idx)
    if attribute is None:
        return None
    value = attribute.get_value(lang=_default_language(product))
    return str(value).strip() if value not in (None, "") else None


def _default_language(product: Product) -> str:
    return product.shop.default_language.iso2.lower() if product.shop.default_language else T9N_DEFAULT_LANG


def _main_product_picture(product: Product | None):
    if product is None:
        return None
    return next((pp for pp in product.pictures.all() if pp.picture_role == PictureRoleEnum.MAIN), None)


def _main_picture_path(product: Product | None) -> str | None:
    """Local filesystem path — the image layer (lookup plan 05) hashes and embeds the bytes.

    Falls back to the storage URL: a non-filesystem backend raises `NotImplementedError` from
    `.path`, and lookup's loader only degrades on `OSError`/`ValueError`, so an unguarded `.path`
    would take a whole embedding batch down instead of skipping one row. `image_path_or_url`
    accepts either shape by name.
    """
    picture = _main_product_picture(product)
    if not (picture and picture.picture.image):
        return None
    image = picture.picture.image
    try:
        return image.path
    except NotImplementedError:
        return image.url


def _main_picture_url(product: Product | None) -> str:
    picture = _main_product_picture(product)
    return picture.picture.image.url if picture and picture.picture.image else ""

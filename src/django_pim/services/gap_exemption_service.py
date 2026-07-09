# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Per-product mute of quality rules (deep mute, etap-13 gap-spawn).

An exemption removes one (product, rule[, language]) pair from detection entirely — the
finding is never written, so badges, rollups and the enrichment ``find_gaps`` candidates
all clear at once. Create/delete re-detect the product **directly** (not via the debounced
signal path): a mute must take effect immediately and independently of
``PimSettings.gaps_enabled``; ``detect_for_product`` already does the silent rollup update.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ObjectDoesNotExist

from ..models import GapDefinition, GapExemption
from .gap_detection_service import detect_for_product
from .product_service import get_product_by_sku


def list_exemptions(*, channel_idx: str, sku: str) -> list[GapExemption]:
    """Exemptions of one product, newest first. Raises ObjectDoesNotExist for an unknown sku."""
    product = get_product_by_sku(channel_idx, sku)
    return list(
        GapExemption.objects.filter(product=product).select_related("definition", "created_by").order_by("-created_at")
    )


def create_exemption(
    *,
    channel_idx: str,
    sku: str,
    definition_key: str,
    language: str | None = None,
    reason: str = "",
    created_by: AbstractBaseUser | None = None,
) -> GapExemption:
    """Mute one rule for one product (``language=None`` = all languages) and re-detect.

    Raises ObjectDoesNotExist for an unknown sku/definition (→ 404) and ValueError for a
    language the channel does not serve or a duplicate exemption (→ 400).
    """
    product = get_product_by_sku(channel_idx, sku)
    try:
        definition = GapDefinition.objects.get(key=definition_key)
    except GapDefinition.DoesNotExist as exc:
        raise ObjectDoesNotExist(f"Gap definition {definition_key!r} not found") from exc

    if language is not None:
        language = language.lower()
        served = {iso2.lower() for iso2 in product.shop.languages.values_list("iso2", flat=True)}
        if language not in served:
            raise ValueError(f"Language {language!r} is not served by channel {channel_idx!r}")

    if GapExemption.objects.filter(product=product, definition=definition, language=language).exists():
        raise ValueError(f"Exemption for {sku!r} / {definition_key!r} / {language!r} already exists")

    exemption = GapExemption.objects.create(
        product=product, definition=definition, language=language, reason=reason, created_by=created_by
    )
    detect_for_product(product)  # finding disappears immediately, rollup repaired silently
    return exemption


def delete_exemption(*, channel_idx: str, exemption_id: int) -> None:
    """Unmute: delete the exemption and re-detect (the finding may reappear).

    The channel check prevents deleting another channel's row through a guessed pk.
    """
    try:
        exemption = GapExemption.objects.select_related("product__shop").get(pk=exemption_id)
    except GapExemption.DoesNotExist as exc:
        raise ObjectDoesNotExist(f"Gap exemption {exemption_id} not found") from exc
    if exemption.product.shop.idx != channel_idx:
        raise ObjectDoesNotExist(f"Gap exemption {exemption_id} not found")

    product = exemption.product
    exemption.delete()
    detect_for_product(product)

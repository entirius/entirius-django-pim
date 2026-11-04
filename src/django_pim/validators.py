# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""SKU validators shared across layers (models, schemas, services).

Leaf module — imports no Django models, so any layer may import it without
violating the dependency direction (API → Services → Models).

The ``idx_normalizator`` checks are wrapped here: their text describes the caller's input, so a refusal
leaves as an ``InvalidRequestError`` (a 400 with that text) instead of a bare ``ValueError``.
"""

from collections.abc import Callable

import idx_normalizator

from django_pim.exceptions import InvalidRequestError

# Literal segments used by SKU-addressed API sub-routes across every module that
# routes by SKU in the URL path (django-pim, -matrix, -pricemanager, -qms,
# -suppliers). A `<path:sku>` converter matches slashes, so a SKU ending in one of
# these would be shadowed by — or shadow — its sub-route. We reject such SKUs at the
# write boundary instead, keeping the routing universal. SKUs are created only here
# (RealProduct.sku) and read by the other modules, so this guard protects all of them.
RESERVED_SKU_SUFFIXES = frozenset(
    {
        # django-pim product sub-routes
        "copy-attributes",
        "copy-translations",
        "add-to-channel",
        "toggle-override",
        "toggle-media-override",
        "links",
        "pictures",
        "files",
        "videos",
        # django-qms
        "edit",
        # django-pricemanager
        "flush-special",
        "preview",
        "history",
        # django-suppliers
        "changes",
        "acknowledge",
        "force-repush",
        "set-preferred-supplier",
        "reset-preferred-to-auto",
    }
)

# Whole-SKU literals that collide with a SIBLING route (not a suffix) — `products/bulk/`
# is the bulk-update endpoint, so a product whose entire SKU is "bulk" would be shadowed.
RESERVED_SKU_WHOLE = frozenset({"bulk"})


def validate_routable_sku(sku: str) -> None:
    """Reject SKUs whose slash-suffix collides with an API sub-route.

    A `<path:sku>` URL converter cannot tell `.../products/X/pictures/` (the pictures
    sub-route of product "X") from the detail of a product literally named
    "X/pictures". The middle of a SKU is unambiguous (`AB/pictures/CD` resolves fine);
    only a reserved trailing segment — optionally followed by an integer pk, as in
    `.../links/<pk>/` — breaks. Raises InvalidRequestError (a ValueError) so callers surface a 400.
    """
    if sku in RESERVED_SKU_WHOLE:
        raise InvalidRequestError(f"SKU '{sku}' collides with the reserved '{sku}/' route. Choose another SKU.")
    if "/" not in sku:
        return
    segments = sku.split("/")
    last = segments[-1]
    reserved = None
    if last in RESERVED_SKU_SUFFIXES:
        reserved = last
    elif last.isdigit() and len(segments) >= 2 and segments[-2] in RESERVED_SKU_SUFFIXES:
        reserved = segments[-2]
    if reserved is not None:
        raise InvalidRequestError(
            f"SKU '{sku}' may not end with the reserved route word '{reserved}' "
            f"— it collides with an API sub-route. Change the SKU suffix."
        )


def _as_refusal(check: Callable[..., None], *args: object, **kwargs: object) -> None:
    """Run an ``idx_normalizator`` check; its ``ValueError`` describes the caller's input, so it leaves as a refusal."""
    try:
        check(*args, **kwargs)
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc


def validate_idx(idx: str, min_len: int = 1, max_len: int = 128) -> None:
    _as_refusal(idx_normalizator.validate_idx, idx, min_len=min_len, max_len=max_len)


def validate_sku(sku: str) -> None:
    _as_refusal(idx_normalizator.validate_sku, sku)


def validate_ean(ean: str | None) -> None:
    _as_refusal(idx_normalizator.validate_ean, ean)

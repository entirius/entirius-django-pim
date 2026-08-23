# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""PIM's call side of the django-lookup module: "what already looks like this?" on product create.

`services/lookup_provider.py` is the mirror image of this file — the read boundary lookup calls
back into. Here PIM is the caller, and lookup stays optional exactly the same way: nothing is
imported at module level, so a service without `entirius-django-lookup` installed simply gets an
empty answer plus a warning.

The hook is advisory by contract (notes §Goal, Product create row): it never blocks a create and
never links anything. It therefore lives in the view, not in `create_product` — the service is also
the import path, which must stay free of a per-row lookup call.
"""

import logging
from dataclasses import asdict

from django.contrib.auth.base_user import AbstractBaseUser

from .. import settings as pim_settings
from ..schemas.requests.product import CreateProductRequest
from ..schemas.responses.lookup import PossibleDuplicateResponse
from ..settings import SYSTEM_FEATURE_BRAND_IDX, SYSTEM_FEATURE_NAME_IDX, T9N_DEFAULT_LANG
from .lookup_provider import MPN_FEATURE_IDX, PHYSICAL_ATTRS

logger = logging.getLogger("process")

# Five is a create-form shortlist, not a search page — the CMS box (/atlas/find) is where an
# operator pages through candidates.
LOOKUP_LIMIT = 5
WARNING_LOOKUP_UNAVAILABLE = "lookup_unavailable"
WARNING_LOOKUP_FAILED = "lookup_failed"
# `LookupQuery` refuses a query without at least one of these; a create carrying none is unmatchable.
_QUERY_SIGNALS = ("ean", "name", "mpn")


def build_query(request: CreateProductRequest, language: str | None = None) -> dict:
    """`LookupQuery` payload for a create request — pure, so it is testable without the module.

    `scope` is left out on purpose: the lookup schema defaults it to every registered kind, which is
    what a create hook wants (PIM catalog *and* unlinked atlas rows).
    """
    lang = language or T9N_DEFAULT_LANG
    payload = {
        "ean": request.ean,
        "name": _attribute_text(request.attributes, SYSTEM_FEATURE_NAME_IDX, lang),
        "brand": _attribute_text(request.attributes, SYSTEM_FEATURE_BRAND_IDX, lang),
        "mpn": _attribute_text(request.attributes, MPN_FEATURE_IDX, lang),
        "attrs": {name: getattr(request, name) for name in PHYSICAL_ATTRS if getattr(request, name)},
        "limit": LOOKUP_LIMIT,
    }
    return {key: value for key, value in payload.items() if value}


def possible_duplicates(
    request: CreateProductRequest, language: str | None = None, user: AbstractBaseUser | None = None
) -> tuple[list[PossibleDuplicateResponse], list[str]]:
    """Candidates the catalogs already hold for this create request, plus any degradation warnings.

    Every failure degrades into a warning: an advisory hook must never cost the caller its product.
    """
    if not pim_settings.PIM_LOOKUP_ON_CREATE:
        return [], []
    payload = build_query(request, language)
    if not any(payload.get(signal) for signal in _QUERY_SIGNALS):
        return [], []
    try:
        return _check(payload, user)
    except ImportError:
        return [], [WARNING_LOOKUP_UNAVAILABLE]
    except Exception:
        logger.exception("pim: duplicate check failed on product create")
        return [], [WARNING_LOOKUP_FAILED]


def _check(payload: dict, user: AbstractBaseUser | None) -> tuple[list[PossibleDuplicateResponse], list[str]]:
    """The only place django-lookup is imported — lazily, so PIM keeps it optional.

    `check` scores the candidates and logs one `DedupDecision` per candidate; PIM only serialises.
    Serialising here, inside the caller's guard, keeps a contract drift a warning rather than a 500
    on a product that was already created.
    """
    from django_lookup.enums import DecisionSource
    from django_lookup.schemas.requests.lookup import LookupQuery
    from django_lookup.services import lookup_service

    result = lookup_service.check(LookupQuery(**payload), user=user, source=DecisionSource.CREATE_HOOK)
    return [PossibleDuplicateResponse(**asdict(hit)) for hit in result.candidates], list(result.warnings)


def _attribute_text(attributes: list, feature_idx: str, language: str) -> str | None:
    """Text of one attribute in the create request, preferring the channel's default language."""
    for attribute in attributes:
        if attribute.feature_idx != feature_idx:
            continue
        if isinstance(attribute.value_txt_t9n, dict):
            values = {lang: str(value).strip() for lang, value in attribute.value_txt_t9n.items() if value}
            return values.get(language) or next(iter(values.values()), None)
        return str(attribute.value_txt).strip() if attribute.value_txt else None
    return None

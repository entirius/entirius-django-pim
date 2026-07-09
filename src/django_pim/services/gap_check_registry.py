# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Gap-check registry — the pure detection rules of the quality highlighter (etap-02).

Each check answers ONE question about a product in one language and returns a
``CheckResult``. Checks never touch the DB themselves — the ``gap_detection_service``
pre-fetches everything into a ``CheckContext`` and orchestrates the calls. This is where
"sygnał, nie szum" lives: applicability (FeatureSet), per-type emptiness, channel
languages, and the cheap local ``inherited`` rule.

Registry metadata per check:
- ``reads_attributes`` — service skips these for ProductCustom (S7).
- ``language_scoped`` — when False the check runs once with ``lang=None`` (e.g. pictures).
- ``allowed_params`` — params allowlist, validated before any lookup (security; params are
  staff/seed-written but this is the boundary).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from ..models import Feature, FeatureScopeEnum, PictureRoleEnum, Product
from ..models.gap_definition import GapCheck
from ..settings import DESCRIPTION_FEATURE_IDXS

logger = logging.getLogger("process")


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one check for one (product, language)."""

    passed: bool
    inherited: bool = False
    source_channel: str | None = None


@dataclass
class CheckContext:
    """Per-product state pre-fetched once by the service. Read-only for checks."""

    product: Product
    channel_idx: str
    is_default_channel: bool
    default_channel_idx: str | None
    inheritance_enabled: bool
    channel_langs: list[str]
    # {lang: {feature_idx: value}} — value already language-resolved via ProductAttribute.get_value
    values_by_lang: dict[str, dict] = field(default_factory=dict)
    feature_by_idx: dict[str, Feature] = field(default_factory=dict)
    member_feature_ids: set[int] = field(default_factory=set)
    overridden_langs_by_idx: dict[str, set] = field(default_factory=dict)
    picture_count_by_role: dict[int, int] = field(default_factory=dict)
    total_picture_count: int = 0
    # alt_text_t9n dict of EVERY product picture (all roles) — picture_alt_present reads these.
    picture_alt_t9ns: list[dict] = field(default_factory=list)
    featureset_is_default: bool = False
    category_count: int = 0


# --- helpers -----------------------------------------------------------------


def _is_empty(value: object) -> bool:
    """Per-type emptiness. bool ``False`` / decimal ``0`` count as SET, not empty."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, list):  # multiselect
        return not [v for v in value if v not in (None, "")]
    return False


def _is_applicable(feature: Feature, ctx: CheckContext) -> bool:
    """Applicability = FeatureSet (NOT is_required). System features always apply."""
    if feature.scope == FeatureScopeEnum.SYSTEM:
        return True
    return feature.id in ctx.member_feature_ids


def _inheritance(feature: Feature, lang: str | None, ctx: CheckContext) -> tuple[bool, str | None]:
    """Cheap, local inherited rule (S6). Invariant: child-empty-inheriting ⇒ default empty,
    so we never query the default channel — only report where to fix it."""
    if ctx.is_default_channel or not ctx.inheritance_enabled:
        return (False, None)
    if feature.exclude_from_inheritance:
        return (False, None)
    is_description = feature.idx in DESCRIPTION_FEATURE_IDXS
    flag = ctx.product.inherit_descriptions if is_description else ctx.product.inherit_attributes
    if not flag:
        return (False, None)
    if lang is not None and lang in ctx.overridden_langs_by_idx.get(feature.idx, []):
        return (False, None)
    return (True, ctx.default_channel_idx)


def _feature_gap(params: dict, lang: str | None, ctx: CheckContext, *, min_length: int) -> CheckResult:
    """Shared body for feature_present (min_length=0) and feature_min_length."""
    feature_idx = params["feature_idx"]
    feature = ctx.feature_by_idx.get(feature_idx)
    if feature is None:
        logger.debug("gap check: unknown feature_idx=%s — skipped", feature_idx)
        return CheckResult(passed=True)
    if not _is_applicable(feature, ctx):
        return CheckResult(passed=True)  # "nie dotyczy"

    value = ctx.values_by_lang.get(lang, {}).get(feature_idx)
    if _is_empty(value):
        failed = True
    elif min_length and isinstance(value, str):
        failed = len(value.strip()) < min_length
    else:
        failed = False

    if not failed:
        return CheckResult(passed=True)
    inherited, source = _inheritance(feature, lang, ctx)
    return CheckResult(passed=False, inherited=inherited, source_channel=source)


# --- checks ------------------------------------------------------------------


def feature_present(params: dict, lang: str | None, ctx: CheckContext) -> CheckResult:
    return _feature_gap(params, lang, ctx, min_length=0)


def feature_min_length(params: dict, lang: str | None, ctx: CheckContext) -> CheckResult:
    return _feature_gap(params, lang, ctx, min_length=int(params.get("min_length", 0)))


def picture_present(params: dict, lang: str | None, ctx: CheckContext) -> CheckResult:
    """Language-neutral: 0 pictures (optionally of a given role) = one gap."""
    role = params.get("role")
    if role:
        # picture_count_by_role is keyed by the stored int (picture_role); normalise the lookup.
        count = ctx.picture_count_by_role.get(int(PictureRoleEnum[role.strip().upper()]), 0)
    else:
        count = ctx.total_picture_count
    if count > 0:
        return CheckResult(passed=True)
    if (not ctx.is_default_channel) and ctx.inheritance_enabled and ctx.product.inherit_images:
        return CheckResult(passed=False, inherited=True, source_channel=ctx.default_channel_idx)
    return CheckResult(passed=False)


def picture_min_count(params: dict, lang: str | None, ctx: CheckContext) -> CheckResult:
    """Language-neutral: a thin gallery — fewer than ``min_count`` pictures (optionally of a role).

    Zero pictures is ``picture_present``'s (critical) gap, NOT this one — never double-flag.
    So this fires only for ``1 <= count < min_count`` ("gallery too thin"), typically a warning.
    """
    min_count = int(params.get("min_count", 0))
    role = params.get("role")
    if role:
        count = ctx.picture_count_by_role.get(int(PictureRoleEnum[role.strip().upper()]), 0)
    else:
        count = ctx.total_picture_count
    if count == 0 or count >= min_count:
        return CheckResult(passed=True)  # 0 = "nie dotyczy" (picture_present's gap); >= min = OK
    if (not ctx.is_default_channel) and ctx.inheritance_enabled and ctx.product.inherit_images:
        return CheckResult(passed=False, inherited=True, source_channel=ctx.default_channel_idx)
    return CheckResult(passed=False)


def picture_alt_present(params: dict, lang: str | None, ctx: CheckContext) -> CheckResult:
    """Language-scoped: every product picture (all roles) must carry a non-empty alt for ``lang``.

    No pictures at all = "not applicable" (that is ``picture_present``'s gap — never double-flag).
    One finding per language covers all missing pictures; the enrichment adapter resolves the
    per-picture detail via its ``{"alts": {picture_pk: alt}}`` snapshot (etap-05-extra).
    """
    if not ctx.picture_alt_t9ns:
        return CheckResult(passed=True)  # "nie dotyczy"
    if all(not _is_empty((alt or {}).get(lang)) for alt in ctx.picture_alt_t9ns):
        return CheckResult(passed=True)
    # Alts ride media inheritance (alt_text_t9n is copied on materialisation) — a fix on an
    # inheriting channel would be clobbered by the next re-materialisation, so point at the source.
    if (not ctx.is_default_channel) and ctx.inheritance_enabled and ctx.product.inherit_images:
        return CheckResult(passed=False, inherited=True, source_channel=ctx.default_channel_idx)
    return CheckResult(passed=False)


def category_present(params: dict, lang: str | None, ctx: CheckContext) -> CheckResult:
    """Structural: the product is assigned to at least one category.

    Language-neutral. Categories are per-channel and never inherited (not one of the
    inherit_* flags), so there's no inherited branch — a product with zero categories
    is simply uncategorised on this channel.
    """
    return CheckResult(passed=ctx.category_count > 0)


def feature_set_default(params: dict, lang: str | None, ctx: CheckContext) -> CheckResult:
    """Structural: the product still sits on the default (placeholder) feature set.

    The classification gap at the head of the cascade — until a real set is assigned,
    attribute gaps are computed on the wrong taxonomy (head of featureset-cascade).
    """
    return CheckResult(passed=not ctx.featureset_is_default)


# --- registry ----------------------------------------------------------------


@dataclass(frozen=True)
class Check:
    fn: Callable[[dict, str | None, CheckContext], CheckResult]
    reads_attributes: bool
    language_scoped: bool
    allowed_params: frozenset[str]


_REGISTRY: dict[str, Check] = {
    GapCheck.FEATURE_PRESENT.value: Check(feature_present, True, True, frozenset({"feature_idx"})),
    GapCheck.FEATURE_MIN_LENGTH.value: Check(feature_min_length, True, True, frozenset({"feature_idx", "min_length"})),
    GapCheck.PICTURE_PRESENT.value: Check(picture_present, False, False, frozenset({"role"})),
    GapCheck.PICTURE_MIN_COUNT.value: Check(picture_min_count, False, False, frozenset({"min_count", "role"})),
    GapCheck.PICTURE_ALT_PRESENT.value: Check(picture_alt_present, False, True, frozenset()),
    GapCheck.CATEGORY_PRESENT.value: Check(category_present, False, False, frozenset()),
    GapCheck.FEATURE_SET_DEFAULT.value: Check(feature_set_default, False, False, frozenset()),
}

_FEATURE_CHECKS = (GapCheck.FEATURE_PRESENT.value, GapCheck.FEATURE_MIN_LENGTH.value)


def get_check(check_key: str) -> Check:
    """Return the registered check or raise ValueError for an unknown key."""
    check = _REGISTRY.get(str(check_key))
    if check is None:
        raise ValueError(f"Unknown gap check_key: {check_key!r}")
    return check


def known_checks(check_keys) -> list[Check]:
    """Registered Check objects for the given keys; unknown keys are skipped, not fatal."""
    return [check for key in check_keys if (check := _REGISTRY.get(str(key)))]


def validate_params(check_key: str, params: dict | None) -> None:
    """Validate a definition's params against the check allowlist before any lookup.

    Raises ValueError on unknown keys, missing feature_idx (feature checks), a bad
    min_length, or an unknown picture role.
    """
    check = get_check(check_key)
    params = params or {}
    invalid = set(params) - check.allowed_params
    if invalid:
        raise ValueError(f"Invalid params for {check_key}: {sorted(invalid)}")
    key = str(check_key)
    if key in _FEATURE_CHECKS and not params.get("feature_idx"):
        raise ValueError(f"{check_key} requires a non-empty 'feature_idx'")
    if key == GapCheck.FEATURE_MIN_LENGTH.value:
        min_length = params.get("min_length")
        if not isinstance(min_length, int) or isinstance(min_length, bool) or min_length < 1:
            raise ValueError("feature_min_length requires a positive integer 'min_length'")
    if key == GapCheck.PICTURE_MIN_COUNT.value:
        min_count = params.get("min_count")
        if not isinstance(min_count, int) or isinstance(min_count, bool) or min_count < 1:
            raise ValueError("picture_min_count requires a positive integer 'min_count'")
    role = params.get("role")
    if role is not None and str(role).strip().upper() not in PictureRoleEnum.__members__:
        raise ValueError(f"Unknown picture role: {role!r}")


def needs_feature_idxs(params: dict | None, check_key: str) -> str | None:
    """The feature_idx a feature-check definition references (None for non-feature checks)."""
    if str(check_key) in _FEATURE_CHECKS:
        return (params or {}).get("feature_idx")
    return None

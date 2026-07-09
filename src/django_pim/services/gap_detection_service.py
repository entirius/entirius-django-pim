# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Gap detection — orchestrates the check registry into materialised findings (etap-02).

``detect_for_product`` is the one entry point: it pre-fetches per-product state once
(zero N+1), runs every active definition in the product's channel scope, writes the sparse
``GapFinding`` rows via a transactional replace, and updates the three ``Product`` rollup
columns through a **silent** ``.update()`` (never ``instance.save()`` — that would fire the
PIM → Matrix signal loop).

Idempotent: two runs produce the same rows and the same rollup.
"""

from __future__ import annotations

from collections import Counter

from django.db import transaction
from django.utils import timezone

from ..models import Feature, FeatureTypeEnum, GapDefinition, GapExemption, GapFinding, Product, ProductClassEnum
from ..models.gap_definition import GapCheck, GapSeverity
from ..models.pim_settings import PimSettings
from . import channel_service
from . import gap_check_registry as registry
from .gap_check_registry import CheckContext

# Sentinel: lets callers inject default_channel=None (no default configured) distinctly from
# "not provided, resolve it yourself" — used by the batch recompute to resolve it once per batch.
_UNSET = object()


def detect_for_product(product: Product, *, definitions=None, default_channel=_UNSET, skip_default=None) -> None:
    """Detect gaps for one product, replace its findings, and update its rollup.

    ``definitions``, ``default_channel`` and ``skip_default`` may be injected by the batch
    recompute service so the per-product queries (active definitions + default channel +
    PimSettings) run once per batch, not per product. When omitted, single-product behaviour
    is identical to etap-02.
    """
    channel = product.shop
    if definitions is None:
        definitions = _active_definitions(channel.idx)
    if skip_default is None:
        skip_default = PimSettings.load().gaps_skip_default_featureset
    if skip_default and product.feature_set.is_default:
        # Cascade sequencing: on the placeholder set, the ONLY actionable gap is "assign a real
        # feature set" — attribute/picture checks would be noise computed on the wrong taxonomy.
        # Narrowed BEFORE the context build so muted products skip the attribute/picture prefetch;
        # their stale findings clear naturally via the replace in _replace_and_rollup.
        definitions = [d for d in definitions if d.check_key == GapCheck.FEATURE_SET_DEFAULT.value]
    ctx = _build_context(product, definitions, default_channel=default_channel)
    is_custom = product.product_class == ProductClassEnum.ProductCustom
    # Deep mute: an exempted (definition, language) pair never produces a finding.
    # (definition_id, None) covers both "all languages" and the language-neutral slot.
    exempted: set[tuple[int, str | None]] = set(
        GapExemption.objects.filter(product=product).values_list("definition_id", "language")
    )

    findings: list[GapFinding] = []
    for definition in definitions:
        try:
            registry.validate_params(definition.check_key, definition.params)
        except ValueError as exc:
            # A misconfigured rule must not poison the whole product evaluation.
            registry.logger.warning("Skipping gap definition %s: %s", definition.key, exc)
            continue
        check = registry.get_check(definition.check_key)
        if is_custom and check.reads_attributes:
            continue  # S7 — custom products are not evaluated on attribute checks
        langs = _resolve_langs(definition, ctx) if check.language_scoped else [None]
        for lang in langs:
            if (definition.id, None) in exempted or (definition.id, lang) in exempted:
                continue
            result = check.fn(definition.params, lang, ctx)
            if not result.passed:
                findings.append(
                    GapFinding(
                        product=product,
                        definition=definition,
                        language=lang,
                        severity=definition.severity,
                        inherited=result.inherited,
                        source_channel=result.source_channel,
                        channel_idx=ctx.channel_idx,
                    )
                )

    _replace_and_rollup(product, findings, evaluated=not is_custom)


# --- internals ---------------------------------------------------------------


def _active_definitions(channel_idx: str) -> list[GapDefinition]:
    """Active definitions whose channel scope covers this channel (null = all channels)."""
    return [
        d
        for d in GapDefinition.objects.filter(active=True).order_by("display_order", "key")
        if d.channels is None or channel_idx in d.channels
    ]


def _resolve_langs(definition: GapDefinition, ctx: CheckContext) -> list[str]:
    """Languages = channel-served languages, optionally narrowed by the definition.

    A definition's ``languages`` are intersected with the channel's — never flag a language
    the channel does not serve.
    """
    if definition.languages:
        wanted = {str(lang).lower() for lang in definition.languages}
        return [lang for lang in ctx.channel_langs if lang in wanted]
    return list(ctx.channel_langs)


def _raw_value(pa, lang: str) -> object:
    """Raw 'is it filled for THIS language' value — no display fallback, no localized label.

    Deliberately NOT ``ProductAttribute.get_value``: that resolver falls back across
    languages (masking a missing per-language description) and returns localized attribute
    names (a missing label translation would look empty). For emptiness we need the raw slot.
    """
    ft = pa.feature.feature_type
    if ft in (FeatureTypeEnum.VARCHAR255_T9N, FeatureTypeEnum.TEXT_T9N):
        return (pa.value_txt_t9n or {}).get(lang)
    if ft == FeatureTypeEnum.JSON_T9N:
        return (pa.value_json or {}).get(lang)
    if ft in (FeatureTypeEnum.VARCHAR255, FeatureTypeEnum.TEXT):
        return pa.value_txt
    if ft == FeatureTypeEnum.BOOL:
        return pa.value_bool
    if ft in (FeatureTypeEnum.DECIMAL, FeatureTypeEnum.TEMPERATURE, FeatureTypeEnum.LENGTH, FeatureTypeEnum.MASS):
        return pa.value_decimal
    if ft == FeatureTypeEnum.DATETIME:
        return pa.value_datetime
    if ft == FeatureTypeEnum.JSON:
        return pa.value_json
    if ft in (FeatureTypeEnum.SELECT, FeatureTypeEnum.MULTISELECT):
        return pa.attribute_id  # presence, independent of label translation
    return None


def _build_context(product: Product, definitions: list[GapDefinition], *, default_channel=_UNSET) -> CheckContext:
    """Pre-fetch everything the checks need in a handful of queries (no N+1)."""
    channel = product.shop
    channel_langs = [iso2.lower() for iso2 in channel.languages.values_list("iso2", flat=True)]

    if default_channel is _UNSET:
        default_channel = channel_service.get_default_channel()
    default_idx = default_channel.idx if default_channel else None
    is_default = bool(default_channel and channel.pk == default_channel.pk)

    # Prefetch only what the active definitions can read — a muted (skip-default) or
    # picture-only catalogue never pays for the attribute/picture queries it won't use.
    needs_attributes = any(c.reads_attributes for c in registry.known_checks(d.check_key for d in definitions))
    picture_checks = {
        GapCheck.PICTURE_PRESENT.value,
        GapCheck.PICTURE_MIN_COUNT.value,
        GapCheck.PICTURE_ALT_PRESENT.value,
    }
    needs_pictures = any(str(d.check_key) in picture_checks for d in definitions)
    needs_categories = any(str(d.check_key) == GapCheck.CATEGORY_PRESENT.value for d in definitions)

    needed_idxs = {idx for d in definitions if (idx := registry.needs_feature_idxs(d.params, d.check_key))}
    feature_by_idx = {f.idx: f for f in Feature.objects.filter(idx__in=needed_idxs)} if needed_idxs else {}
    member_feature_ids = set(product.feature_set.features.values_list("id", flat=True)) if needs_attributes else set()

    pas = (
        list(
            product.products_attributes.exclude(feature__feature_type=FeatureTypeEnum.UNKNOWN).select_related(
                "feature", "attribute"
            )
        )
        if needs_attributes
        else []
    )
    values_by_lang: dict[str, dict] = {}
    for lang in channel_langs:
        values: dict = {}
        for pa in pas:
            idx = pa.feature.idx
            raw = _raw_value(pa, lang)
            if pa.feature.feature_type == FeatureTypeEnum.MULTISELECT:
                values.setdefault(idx, []).append(raw)
            else:
                values[idx] = raw
        values_by_lang[lang] = values
    # Multiselect has several rows per idx → merge their override langs, don't overwrite.
    overridden_by_idx: dict[str, set] = {}
    for pa in pas:
        overridden_by_idx.setdefault(pa.feature.idx, set()).update(pa.overridden_langs or [])

    # One query serves both picture checks: roles for picture_present, alts for picture_alt_present.
    picture_rows = list(product.pictures.values_list("picture_role", "alt_text_t9n")) if needs_pictures else []
    roles = [role for role, _ in picture_rows]

    category_count = product.product_in_category.count() if needs_categories else 0

    return CheckContext(
        product=product,
        channel_idx=channel.idx,
        is_default_channel=is_default,
        default_channel_idx=default_idx,
        inheritance_enabled=channel.inheritance_enabled,
        channel_langs=channel_langs,
        values_by_lang=values_by_lang,
        feature_by_idx=feature_by_idx,
        member_feature_ids=member_feature_ids,
        overridden_langs_by_idx=overridden_by_idx,
        picture_count_by_role=dict(Counter(roles)),
        total_picture_count=len(roles),
        picture_alt_t9ns=[alt or {} for _, alt in picture_rows],
        featureset_is_default=product.feature_set.is_default,
        category_count=category_count,
    )


_SEVERITY_ORDER = {GapSeverity.CRITICAL: 2, GapSeverity.WARNING: 1}


def _worst_severity(findings: list[GapFinding]) -> str | None:
    if not findings:
        return None
    return max((f.severity for f in findings), key=lambda s: _SEVERITY_ORDER.get(s, 0))


@transaction.atomic
def _replace_and_rollup(product: Product, findings: list[GapFinding], *, evaluated: bool) -> None:
    """Idempotent replace of this product's findings + silent rollup update."""
    GapFinding.objects.filter(product=product).delete()
    if findings:
        GapFinding.objects.bulk_create(findings)
    # Silent: .update() does NOT fire post_save → no PIM/Matrix signal loop.
    Product.objects.filter(pk=product.pk).update(
        gap_count=len(findings),
        gap_worst_severity=_worst_severity(findings),
        gap_evaluated_at=timezone.now() if evaluated else None,
    )

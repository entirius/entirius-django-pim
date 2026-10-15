# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""PIM adapter for the django-enrichment bus (decision D1, the *referential* adapter).

The enrichment bus never imports PIM. It loads this module lazily by dotted path from
`settings.ENRICHMENT_ADAPTERS = {"pim": "django_pim.services.enrichment_adapter"}` and calls the
five module-level functions below (duck-typed against `django_enrichment.adapters.base`). This file
therefore imports nothing from `django-enrichment` — the dependency points one way: bus → contract.

PIM locator / value convention (the bus treats both as opaque — only this module reads them):

- `subject_ref`     = product SKU
- `target_kind`     = `"attribute_value"` (text) | `"picture"` (media, etap-08)
                    | `"feature_set"` (classification, featureset-cascade etap-02)
                    | `"category"` (classification — AI picks existing categories, `{"category_idxs": [...]}`)
                    | `"picture_alt"` (alt texts, featureset-cascade etap-05-extra)
                    | `"video"` (media — a generated product video attached as a VIDEO file, AI POC A1)
- `target_locator`  = `{"channel": <channel_idx>, "language": <iso2>, "feature_idx": <idx>}`  (text)
                    | `{"channel": <channel_idx>}`                                            (picture)
                    | `{"channel": <channel_idx>}`                                            (feature_set)
                    | `{"channel": <channel_idx>, "language": <iso2>}`                        (picture_alt)
                    | `{"channel": <channel_idx>}`                                            (video)
                    | `{"channel": <channel_idx>, "language": None, "feature_idx": <idx>}`  (select / multiselect)
- `proposed_value`  = `{"text": <new value for that single language>}`                        (text)
                    | `{"option": <Attribute.idx>}` / `{"options": [<Attribute.idx>, ...]}`   (select / multiselect)
                    | `{"op": "replace_main", "alt_t9n": {<iso2>: <alt>}}`                    (picture)
                    | `{"featureset_idx": <idx of an existing FeatureSet>}`                   (feature_set)
                    | `{"alts": {"<picture_pk>": <alt for that single language>}}`            (picture_alt)
- `current_snapshot`= `{"text": <raw stored value for that language, "" if absent>}`          (text)
                    | `{"option": <idx, "" if none>}` / `{"options": [<sorted idxs>]}`        (select / multiselect)
                    | `{"sha1", "role", "position", "alt_t9n", "url"}` of the old main, `{}` if none (picture)
                    | `{"featureset_idx": <current idx, "" if product missing>}`              (feature_set)
                    | `{"alts": {"<picture_pk>": <stored alt, "" if absent>}}` of ALL pictures (picture_alt)
                    | `{"files": [<stored names of the VIDEO files linked to the product>]}`  (video)

Video (`target_kind == "video"`): like `picture`, the binary is staged in the bus. `apply` uploads it
via `product_file_service.upload_file` (type VIDEO, label = product name) and links it. `revert`
unlinks the files present in `applied_snapshot` but not in `current_snapshot` — the staged copy is
gone after apply, so the snapshot diff is the only record of what this proposal linked.

Optional callables for the AI workers: `build_context` (compact product facts for a prompt),
`main_picture` (bytes + mime of the main picture, input for the video kind), `list_pictures` / `picture`
(the product's pictures to choose from, and one of them by ref, for a video of a chosen picture) and the field catalog
`describe_fields` / `channel_languages` / `make_locator` / `field_key` (writable text and select features),
and `category_of` (the product's first category as a memory ref, so category-scoped SEO briefs are shared).

Classification (`target_kind == "feature_set"`, etap-02): the FIRST classification gap — the AI
resolves it by picking an existing PIM entity (a `FeatureSet` idx from `GET feature-sets/`), not by
writing free text. The locator carries no language (classification is language-neutral; the matching
`feature_set_default` findings are written with `language=NULL`). Apply writes via
`product.save(update_fields=["feature_set"])` — deliberately NOT a silent `.update()` (decision PO
2026-06-10): the post_save signals must fire so the gap recompute clears the structural finding and
surfaces the now-applicable attribute gaps (the cascade), and Matrix re-syncs set membership. No
signal loop: the silent-`.update()` rule covers only rollup columns written INSIDE detection.

Alt texts (`target_kind == "picture_alt"`, etap-05-extra): one proposal covers ALL pictures of the
product for ONE language (the `picture_alt_present` finding has the same granularity). Picture pks
travel as STRING keys — `proposed_value`/`current_snapshot` are JSON columns on the proposal, and
JSON object keys are always strings. Apply is per-picture read-merge-write on `alt_text_t9n`
(sibling languages and pictures absent from the map are never touched) wrapped in one
`transaction.atomic()` — an unknown/foreign picture_pk raises `ValueError` with NO partial write.
Writes go through `pp.save(update_fields=["alt_text_t9n"])` so post_save fires the gap recompute
(the finding clears) and the Matrix sync (the read model picks the new alt up); both handlers are
gated and debounced — no loop risk (same reasoning as `feature_set` below).

Media (`target_kind == "picture"`, etap-08): the binary is staged in the BUS, not here. `apply`
reads it via `proposal.open_staged_file()` (no import of the bus), uploads it through
`product_picture_service.upload_picture` (SHA1 dedup), links it as the new main, and drops the old
main link. The old `Picture` row survives (kept in the pool) as the single-level undo anchor — GC is
the bus's cleanup beat (etap-10). One main per `(sku, channel)`; languages ride in `alt_text_t9n`
(picture link `language=None`), so the locator carries no language for pictures.

Scope spec (for `resolve_targets` / `find_gaps`):

- `{"mode": "list",   "module": "pim", "channel": <idx>, "refs": [sku, ...]}`
- `{"mode": "filter", "module": "pim", "channel": <idx>, "filters": {<list_products kwargs>}}`
- `{"mode": "gap",    "module": "pim", "check": <GapDefinition.key>, "scope": {"channel": <idx>, "language": <iso2>?}}`
  (`find_gaps` reads materialised `GapFinding` rows — see its docstring for the candidate shape)

Two non-obvious rules this adapter owns (the bus stays dumb about them):

1. **Read-merge-write.** PIM's write path (`product_service.update_product` → `_set_product_attributes`)
   deletes and recreates the whole attribute row per feature. Writing a single language would wipe the
   others, so `apply`/`revert` always merge the proposed language into the full `value_txt_t9n` dict.
2. **Inheritance override.** A write on a *secondary* (non-default) channel whose product inherits the
   relevant feature would be clobbered by the next materialisation. So after writing, the language is
   marked in `overridden_langs` — but ONLY when inheritance is actually enabled (channel switch + flag,
   feature not excluded) on a non-default channel (decision PO: don't write override metadata where
   it's meaningless).
"""

import io

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import F, Q, Window
from django.db.models.functions import RowNumber
from django.utils.html import strip_tags
from PIL import Image

from ..models import (
    Attribute,
    Channel,
    Feature,
    FeatureInFeatureSet,
    FeatureScopeEnum,
    FeatureSet,
    FeatureTypeEnum,
    FileRoleEnum,
    GapCheck,
    GapDefinition,
    GapFinding,
    Picture,
    PictureRoleEnum,
    Product,
    ProductAttribute,
    ProductFile,
    ProductInCategory,
    ProductPicture,
)
from ..settings import (
    DESCRIPTION_FEATURE_IDXS,
    SEO_FEATURE_IDXS,
    SYSTEM_FEATURE_CANONICAL_URL_IDX,
    SYSTEM_FEATURE_NAME_IDX,
    SYSTEM_FEATURE_OG_IMAGE_IDX,
    SYSTEM_FEATURE_URL_KEY_IDX,
)
from . import product_file_service, product_picture_service, product_service

# How many SKUs a worker pulls per `resolve_targets` page. The bus passes `page`; we never
# materialise the whole catalogue.
_PAGE_SIZE = 100

# `attribute_value` writes translatable text and select/multiselect options only. Scalar features
# fail loud rather than silently no-op (a t9n payload sent to a non-t9n feature would be dropped by
# `_set_product_attributes`).
_T9N_TEXT_TYPES = frozenset({FeatureTypeEnum.VARCHAR255_T9N, FeatureTypeEnum.TEXT_T9N})
_SELECT_TYPES = frozenset({FeatureTypeEnum.SELECT, FeatureTypeEnum.MULTISELECT})

# Field catalog shape per writable feature type: (type, max_length, translatable). TEXT_T9N is
# edited as HTML in the CMS (wysiwyg), VARCHAR255_T9N as plain text capped by its column.
_FIELD_SHAPES = {
    FeatureTypeEnum.VARCHAR255_T9N: ("text", 255, True),
    FeatureTypeEnum.TEXT_T9N: ("html", None, True),
    FeatureTypeEnum.SELECT: ("select", None, False),
    FeatureTypeEnum.MULTISELECT: ("multiselect", None, False),
}
_MAX_OPTIONS = 200
# SEO text lands in meta tags: plain text, capped, whatever the storage type.
_SEO_TEXT_SHAPE = ("text", 255, True)
# System fields that drive routes and SEO, not content — never offered to (or addressable by) the AI.
_NON_WRITABLE_IDXS = frozenset(
    {SYSTEM_FEATURE_URL_KEY_IDX, SYSTEM_FEATURE_CANONICAL_URL_IDX, SYSTEM_FEATURE_OG_IMAGE_IDX}
)

# Namespace of `category_of` refs: memory entries share `subject_module="pim"` with SKUs.
_CATEGORY_REF_PREFIX = "category:"

# list_products kwargs an external scope may drive. Anything else in `filters` is ignored rather
# than passed through (avoids a worker injecting arbitrary kwargs).
_ALLOWED_FILTERS = frozenset({"search", "is_enabled", "visibility", "product_class", "category_idx", "has_media"})


def _locator(target_locator: dict) -> tuple[str, str, str]:
    """Unpack the PIM locator. Raises KeyError early if a worker sends an incomplete address."""
    return target_locator["channel"], target_locator["language"], target_locator["feature_idx"]


def read_current(*, subject_ref: str, target_kind: str, target_locator: dict) -> dict:
    """Authoritative current value of one target — dispatches by `target_kind` (text / picture /
    feature_set; snapshot shapes in the module docstring, helpers document their own rules).

    Text reads the RAW `value_txt_t9n[language]` (never `get_value`, which falls back across
    languages — that would make drift comparisons and undo restore the wrong string). Missing
    product / feature / language all collapse to `{"text": ""}` so the bus can still diff and
    detect drift.
    """
    if target_kind == "picture":
        return _read_current_picture(subject_ref, target_locator)
    if target_kind == "feature_set":
        return _read_current_feature_set(subject_ref, target_locator)
    if target_kind == "category":
        return _read_current_category(subject_ref, target_locator)
    if target_kind == "picture_alt":
        return _read_current_picture_alt(subject_ref, target_locator)
    if target_kind == "video":
        return _read_current_video(subject_ref, target_locator)
    if target_kind != "attribute_value":
        return {"text": ""}
    channel_idx, language, feature_idx = _locator(target_locator)
    feature = Feature.objects.filter(idx=feature_idx).first()
    if feature is not None and feature.feature_type in _SELECT_TYPES:
        return _read_current_select(subject_ref, channel_idx, feature)
    try:
        product = product_service.get_product_by_sku(channel_idx, subject_ref)
    except ObjectDoesNotExist:
        return {"text": ""}
    attr = ProductAttribute.objects.filter(product=product, feature__idx=feature_idx).first()
    if attr is None:
        return {"text": ""}
    raw = attr.value_txt_t9n or {}
    return {"text": raw.get(language) or ""}


def apply(proposal) -> None:
    """Write `proposed_value` into the target (text for one language, or select/multiselect options).

    The ONLY place enrichment writes back to PIM. Drift is already checked by the bus
    (`apply_service.apply`) before we get here. Read-merge-write + inheritance override (see module
    docstring). Raises for unsupported feature types / missing product so misuse is loud.
    """
    if proposal.target_kind == "picture":
        _apply_picture(proposal)
        return
    if proposal.target_kind == "video":
        _apply_video(proposal)
        return
    if proposal.target_kind == "feature_set":
        _write_feature_set(
            proposal.target_locator["channel"],
            subject_ref=proposal.subject_ref,
            featureset_idx=proposal.proposed_value.get("featureset_idx"),
        )
        return
    if proposal.target_kind == "category":
        category_idxs = (proposal.proposed_value or {}).get("category_idxs")
        if not category_idxs:
            # Apply must add ≥1 category — an empty proposal would strip the product's categories
            # and never clear the gap (worker misuse). Restoring "no categories" is revert's job.
            raise ValueError("category apply requires a non-empty 'category_idxs' list")
        _write_categories(
            proposal.target_locator["channel"], subject_ref=proposal.subject_ref, category_idxs=category_idxs
        )
        return
    if proposal.target_kind == "picture_alt":
        alts = (proposal.proposed_value or {}).get("alts")
        if not alts:
            # An apply with nothing to write is always worker misuse — fail loud (unlike revert,
            # where an empty snapshot legitimately means "no pictures existed at intake").
            raise ValueError("picture_alt apply requires a non-empty 'alts' map")
        if any(isinstance(alt, str) and not alt.strip() for alt in alts.values()):
            # An empty/whitespace alt would apply "successfully" yet never clear the finding
            # (the check treats "" as missing) — the enrichment loop would respawn the candidate
            # forever. Only revert may write "" (restoring a snapshotted empty state).
            raise ValueError("picture_alt apply requires non-empty alt strings ('' is restore-only)")
        _write_picture_alts(
            proposal.target_locator["channel"],
            subject_ref=proposal.subject_ref,
            language=proposal.target_locator["language"],
            alts=alts,
        )
        return
    _reject_non_writable(proposal.target_locator)
    _reject_inherited_select_clear(
        proposal.target_locator, subject_ref=proposal.subject_ref, value=proposal.proposed_value
    )
    _write_attribute(proposal.target_locator, subject_ref=proposal.subject_ref, value=proposal.proposed_value)


def revert(proposal) -> None:
    """Restore the target to `current_snapshot` (single-level undo — etap-09 deepens this)."""
    if proposal.target_kind == "picture":
        _revert_picture(proposal)
        return
    if proposal.target_kind == "video":
        _revert_video(proposal)
        return
    if proposal.target_kind == "feature_set":
        _write_feature_set(
            proposal.target_locator["channel"],
            subject_ref=proposal.subject_ref,
            featureset_idx=proposal.current_snapshot.get("featureset_idx"),
        )
        return
    if proposal.target_kind == "category":
        # Restore the snapshotted set — an empty list IS the restore (the product had no categories
        # before apply, since category_present fired), so this always executes (unlike picture_alt).
        _write_categories(
            proposal.target_locator["channel"],
            subject_ref=proposal.subject_ref,
            category_idxs=(proposal.current_snapshot or {}).get("category_idxs") or [],
        )
        return
    if proposal.target_kind == "picture_alt":
        alts = (proposal.current_snapshot or {}).get("alts")
        if not alts:
            return  # no pictures existed at intake — nothing to restore (vs feature_set hard-error)
        _write_picture_alts(
            proposal.target_locator["channel"],
            subject_ref=proposal.subject_ref,
            language=proposal.target_locator["language"],
            alts=alts,
        )
        return
    # An empty text snapshot restores "" (as before); select snapshots always carry their key.
    snapshot = {"text": "", **(proposal.current_snapshot or {})}
    _write_attribute(proposal.target_locator, subject_ref=proposal.subject_ref, value=snapshot)


def _read_current_picture(subject_ref: str, target_locator: dict) -> dict:
    """Snapshot the displaced main picture (sha1 drives drift; url feeds the CMS before-preview).

    Empty `{}` when the product has no main — comparable with `!=` for drift and renders as "no
    current image" in review. `sha1`/`url` are stable (PIM stores files by sha1) so the snapshot is
    safe both as a drift key and as a displayable URL.
    """
    channel_idx = target_locator["channel"]
    try:
        product = product_service.get_product_by_sku(channel_idx, subject_ref)
    except ObjectDoesNotExist:
        return {}
    pp = product.main_product_picture
    if pp is None:
        return {}
    pic = pp.picture
    return {
        "sha1": pic.sha1 or "",
        "role": "main",
        "position": pp.position,
        "alt_t9n": pp.alt_text_t9n or {},
        "url": pic.image.url if pic.image else "",
    }


def _apply_picture(proposal) -> None:
    """`op=replace_main`: staged binary → `upload_picture` (SHA1 dedup) → link as main → drop old main.

    The old `Picture` row is intentionally kept (only its `ProductPicture` link is removed) so undo
    (`revert`) can re-link it. Runs inside the bus's apply transaction.
    """
    channel_idx = proposal.target_locator["channel"]
    sku = proposal.subject_ref
    value = proposal.proposed_value or {}
    op = value.get("op", "replace_main")
    if op != "replace_main":
        raise ValueError(f"unsupported picture op {op!r} (only 'replace_main')")

    staged = proposal.open_staged_file()
    try:
        picture = product_picture_service.upload_picture(staged)
    finally:
        staged.close()

    product = product_service.get_product_by_sku(channel_idx, sku)
    # Drop the old main LINK only — Picture stays in the pool as the undo anchor (GC = etap-10).
    ProductPicture.objects.filter(product=product, picture_role=PictureRoleEnum.MAIN).delete()
    product_picture_service.link_picture_to_product(
        channel_idx,
        sku,
        picture.pk,
        picture_role="main",
        position=0,
        language_iso2=None,
        alt_text_t9n=value.get("alt_t9n") or {},
    )


def _revert_picture(proposal) -> None:
    """Undo `replace_main`: drop the current main, re-link the old `Picture` from `current_snapshot`.

    Looks the old picture up by the snapshot `sha1` (still in the pool — GC is etap-10). If the
    snapshot is empty (no prior main) just removes the current main.
    """
    channel_idx = proposal.target_locator["channel"]
    sku = proposal.subject_ref
    snapshot = proposal.current_snapshot or {}
    product = product_service.get_product_by_sku(channel_idx, sku)
    ProductPicture.objects.filter(product=product, picture_role=PictureRoleEnum.MAIN).delete()

    sha1 = snapshot.get("sha1")
    if not sha1:
        return
    old = Picture.objects.filter(sha1=sha1).first()
    if old is None:
        return
    product_picture_service.link_picture_to_product(
        channel_idx,
        sku,
        old.pk,
        picture_role="main",
        position=snapshot.get("position", 0),
        language_iso2=None,
        alt_text_t9n=snapshot.get("alt_t9n") or {},
    )


# Reverse-relation ACCESSOR names (not model names) OWNED by a `Picture` — its own generated thumbs
# and download-url provenance. They cascade-delete with it and are NOT external "uses", so they must
# not block GC. Every OTHER reverse relation means the image is still displayed somewhere (the model
# → accessor map: ProductPicture→products, AttributePicture→attributes, ProductAttributeImage→
# product_attribute_picture, ProductCategoryPicture→product_categories, ProductAttributeCustomImage→
# product_attribute_custom_picture, and anything added later) — keep the Picture.
# To extend this denylist, add the reverse ACCESSOR name (`rel.get_accessor_name()`), not the model name.
_OWNED_PICTURE_RELATIONS = frozenset({"picture_thumbs", "downloads_urls"})


def release_undo_anchor(proposal) -> int:
    """GC the `Picture`(s) this proposal displaced/orphaned, once retention expires (etap-10 cleanup).

    The bus calls this for a picture proposal it is about to prune (undo has expired). Status-agnostic
    by design — it offers BOTH snapshots' pictures to a reference-guarded GC, so either side is safe:
    for an `applied` proposal `current_snapshot.sha1` is the displaced old main (now unreferenced →
    reclaimed) while `applied_snapshot.sha1` is the new live main (still linked → kept); for a
    `reverted` proposal it's the mirror. Text snapshots carry no `sha1`, so non-picture proposals
    no-op. Returns the count of `Picture` rows reclaimed (0–2).
    """
    if proposal.target_kind != "picture":
        return 0
    reclaimed = 0
    for snapshot in (proposal.current_snapshot, proposal.applied_snapshot):
        reclaimed += _gc_orphan_picture((snapshot or {}).get("sha1") or "")
    return reclaimed


def _gc_orphan_picture(sha1: str) -> int:
    """Delete the `Picture` for `sha1` iff nothing outside its own derived rows references it.

    SHA1 dedup is shared across products/attributes/categories, so a Picture displaced from one
    product's main may still be in use elsewhere — deleting it would corrupt those. Scans EVERY
    reverse relation (so a future referencing model can't silently make GC unsafe) and bails if any
    non-owned one has rows. `Picture.delete()` removes the physical file + thumbs (post_delete signal
    + model delete). Returns 1 if deleted, else 0.
    """
    if not sha1:
        return 0
    picture = Picture.objects.filter(sha1=sha1).first()
    if picture is None:
        return 0
    for rel in picture._meta.related_objects:
        accessor = rel.get_accessor_name()
        if accessor in _OWNED_PICTURE_RELATIONS:
            continue
        if getattr(picture, accessor).exists():
            return 0
    # Delete via the QuerySet, not `picture.delete()`: the model's `delete()` override is broken
    # (`self.thumbs` does not exist on Picture — finding, see roadmap § Changelog). The QuerySet
    # delete still fires the `post_delete` receiver that removes the physical file, and cascades the
    # owned rows (thumbs, download-urls). We only reach here with zero external references.
    Picture.objects.filter(pk=picture.pk).delete()
    return 1


def _get_feature(feature_idx: str) -> Feature:
    try:
        return Feature.objects.get(idx=feature_idx)
    except Feature.DoesNotExist as exc:
        raise ValueError(f"unknown feature_idx {feature_idx!r}") from exc


def _write_attribute(target_locator: dict, *, subject_ref: str, value: dict) -> None:
    """Shared `attribute_value` write (apply + revert): select options or one language of text."""
    channel_idx, language, feature_idx = _locator(target_locator)
    feature = _get_feature(feature_idx)
    if feature.feature_type in _SELECT_TYPES:
        _write_select(channel_idx, subject_ref=subject_ref, feature=feature, value=value)
        return
    _write_text(channel_idx, subject_ref=subject_ref, feature=feature, language=language, text=value.get("text"))


def _write_text(channel_idx: str, *, subject_ref: str, feature: Feature, language: str, text) -> None:
    """Read-merge-write of one language + override.

    `text` must be a plain string — `value_txt_t9n` is a `{lang: str}` map and every reader (get_value,
    Matrix sync, storefront) indexes it as a scalar. Writing a dict/list/None would corrupt the field
    for all consumers, so reject it loudly here rather than silently persisting structured JSON.
    """
    if not isinstance(text, str):
        raise ValueError(
            f"enrichment_adapter expects a string value for {feature.idx!r}/{language!r}, got {type(text).__name__}"
        )
    if feature.feature_type not in _T9N_TEXT_TYPES:
        raise ValueError(
            f"enrichment_adapter writes translatable text only (or select options); feature {feature.idx!r} is "
            f"feature_type={feature.feature_type} (expected VARCHAR255_T9N, TEXT_T9N, SELECT or MULTISELECT)"
        )
    if not isinstance(language, str) or not language:
        raise ValueError(f"translatable feature {feature.idx!r} needs a language in the locator")
    language = language.lower()

    product = product_service.get_product_by_sku(channel_idx, subject_ref)
    _require_applicable(product, feature, subject_ref)
    existing = ProductAttribute.objects.filter(product=product, feature=feature).first()
    merged = dict(existing.value_txt_t9n or {}) if existing is not None else {}
    merged[language] = text

    product_service.update_product(
        channel_idx, subject_ref, attributes=[{"feature_idx": feature.idx, "value_txt_t9n": merged}]
    )

    _mark_overridden_if_inheriting(product, feature, language)


def _read_current_select(subject_ref: str, channel_idx: str, feature: Feature) -> dict:
    """Selected option idxs (sorted, so drift ignores row order); missing product → empty value."""
    try:
        product = product_service.get_product_by_sku(channel_idx, subject_ref)
    except ObjectDoesNotExist:
        return _select_value(feature, [])
    idxs = ProductAttribute.objects.filter(product=product, feature=feature, attribute__isnull=False).values_list(
        "attribute__idx", flat=True
    )
    return _select_value(feature, sorted(idxs))


def _select_value(feature: Feature, idxs: list[str]) -> dict:
    if feature.feature_type == FeatureTypeEnum.MULTISELECT:
        return {"options": idxs}
    return {"option": idxs[0] if idxs else ""}


def _requested_options(feature: Feature, value: dict) -> list[str]:
    """Option idxs from `{"option": str}` (single, "" clears) or `{"options": [str]}` (multi, [] clears)."""
    if feature.feature_type == FeatureTypeEnum.MULTISELECT:
        options = value.get("options")
        if not isinstance(options, list) or not all(isinstance(o, str) and o for o in options):
            raise ValueError(f"multiselect {feature.idx!r} expects 'options' as a list of option idxs, got {options!r}")
        return list(dict.fromkeys(options))
    option = value.get("option")
    if not isinstance(option, str):
        raise ValueError(f"select {feature.idx!r} expects 'option' as an option idx string, got {option!r}")
    return [option] if option else []


def _write_select(channel_idx: str, *, subject_ref: str, feature: Feature, value: dict) -> None:
    """Replace the feature's options (validated against the feature — unknown idx fails loud)."""
    idxs = _requested_options(feature, value)
    known = set(Attribute.objects.filter(feature=feature, idx__in=idxs).values_list("idx", flat=True))
    if unknown := [idx for idx in idxs if idx not in known]:
        raise ValueError(f"unknown option(s) {unknown} for feature {feature.idx!r}")
    product = product_service.get_product_by_sku(channel_idx, subject_ref)
    _require_applicable(product, feature, subject_ref)
    if feature.feature_type == FeatureTypeEnum.MULTISELECT:
        payload = {"feature_idx": feature.idx, "attribute_idxs": idxs}
    else:
        payload = {"feature_idx": feature.idx, "attribute_idx": idxs[0] if idxs else None}
    product_service.update_product(channel_idx, subject_ref, attributes=[payload])
    _mark_overridden_if_inheriting(product, feature, None)


def _require_applicable(product, feature: Feature, subject_ref: str) -> None:
    """Refuse writes to a feature the product's FeatureSet does not contain (PIM: "not applicable").

    System features are implicit (never in FeatureInFeatureSet) and always apply — same rule as gaps.
    """
    if feature.scope == FeatureScopeEnum.SYSTEM:
        return
    if not FeatureInFeatureSet.objects.filter(feature_set_id=product.feature_set_id, feature=feature).exists():
        raise ValueError(f"feature {feature.idx!r} is not in the feature set of {subject_ref!r}")


def _reject_non_writable(target_locator: dict) -> None:
    """Apply-only guard: route/SEO system fields stay out of reach of any proposal, however it was built
    (`make_locator` refuses them too, but a posted proposal or a legacy `field` locator bypasses it).
    Revert stays open so a snapshot taken before this guard can still be restored."""
    _channel_idx, _language, feature_idx = _locator(target_locator)
    if feature_idx in _NON_WRITABLE_IDXS:
        raise ValueError(f"feature {feature_idx!r} is not a writable field (system route/SEO field)")


def _reject_inherited_select_clear(target_locator: dict, *, subject_ref: str, value: dict) -> None:
    """Apply-only guard: a cleared select on an inheriting secondary channel leaves no row to mark
    overridden, so the next materialisation would silently copy the source values back."""
    channel_idx, _language, feature_idx = _locator(target_locator)
    feature = _get_feature(feature_idx)
    if feature.feature_type not in _SELECT_TYPES or _requested_options(feature, value):
        return
    if _inherits(product_service.get_product_by_sku(channel_idx, subject_ref), feature):
        raise ValueError("cannot clear an inherited select on a secondary channel; disable attribute inheritance first")


def _inherits(product, feature: Feature) -> bool:
    """True when a write to `feature` on this product would be clobbered by materialisation
    (same conditions as `inheritance_service`)."""
    if product.shop.is_default or not product.shop.inheritance_enabled or feature.exclude_from_inheritance:
        return False
    if feature.idx in DESCRIPTION_FEATURE_IDXS:
        return product.inherit_descriptions
    return product.inherit_attributes


def _mark_overridden_if_inheriting(product, feature: Feature, language: str | None) -> None:
    """Mark the write overridden so materialisation won't clobber it — only where it matters.

    The marker is the language for text and `"*"` for language-neutral (select) values, matching
    `inheritance_service`. No-op on the default channel (it's the inheritance source) or when the
    product does not inherit the relevant flag (description vs attribute). The rows were
    deleted+recreated by the write, so we re-fetch them and set `overridden_langs` directly rather than
    going through `toggle_language_override` (which raises unless inheritance is enabled and the
    attribute exists).
    """
    if not _inherits(product, feature):
        return
    marker = language or "*"
    for attr in ProductAttribute.objects.filter(product=product, feature=feature):
        overridden = set(attr.overridden_langs or [])
        if marker in overridden:
            continue
        attr.overridden_langs = sorted(overridden | {marker})
        attr.save(update_fields=["overridden_langs"])


def _read_current_feature_set(subject_ref: str, target_locator: dict) -> dict:
    """Snapshot the product's current feature-set idx (drift baseline for classification proposals).

    Missing product collapses to `{"featureset_idx": ""}` (mirrors the text path) so the bus can
    still diff and detect drift.
    """
    channel_idx = target_locator["channel"]
    try:
        product = product_service.get_product_by_sku(channel_idx, subject_ref)
    except ObjectDoesNotExist:
        return {"featureset_idx": ""}
    return {"featureset_idx": product.feature_set.idx}


def _write_feature_set(channel_idx: str, *, subject_ref: str, featureset_idx) -> None:
    """Shared classification write used by both apply and revert.

    `product.save(update_fields=["feature_set"])` — NOT a silent `.update()` — so post_save fires
    the gap recompute (the cascade: structural finding clears, attribute gaps appear) and the Matrix
    sync (set membership drives filterables). Both handlers are gated and debounced; no loop risk
    (see module docstring). Unknown/empty idx fails loud — misclassification must never no-op.
    Unlike text ("" restores empty) and picture ({} drops the main), feature_set has NO empty
    terminal state (the FK is non-null), so an empty snapshot on revert is a hard ValueError by design.
    """
    if not isinstance(featureset_idx, str) or not featureset_idx:
        raise ValueError(f"enrichment_adapter expects a non-empty featureset_idx string, got {featureset_idx!r}")
    try:
        feature_set = FeatureSet.objects.get(idx=featureset_idx)
    except FeatureSet.DoesNotExist as exc:
        raise ValueError(f"unknown featureset_idx {featureset_idx!r}") from exc

    product = product_service.get_product_by_sku(channel_idx, subject_ref)
    product.feature_set = feature_set
    product.save(update_fields=["feature_set"])


def _read_current_category(subject_ref: str, target_locator: dict) -> dict:
    """Snapshot the product's current category idxs (drift baseline + undo for classification).

    Missing product collapses to `{"category_idxs": []}` so the bus can still diff; an empty list is
    the legitimate pre-apply state (the gap fires precisely when the product has no categories).
    """
    channel_idx = target_locator["channel"]
    try:
        product = product_service.get_product_by_sku(channel_idx, subject_ref)
    except ObjectDoesNotExist:
        return {"category_idxs": []}
    return {"category_idxs": list(product.product_in_category.values_list("category__idx", flat=True))}


def _write_categories(channel_idx: str, *, subject_ref: str, category_idxs: list) -> None:
    """Shared classification write (apply + revert). Full-replace of the product's categories via the
    service (PATCH semantics), which fires the gap recompute + Matrix sync. An empty list is allowed
    here (revert restoring "no categories"); the apply path guards against empty before calling."""
    product_service.update_product(channel_idx, subject_ref, category_idxs=list(category_idxs))


def _read_current_picture_alt(subject_ref: str, target_locator: dict) -> dict:
    """Snapshot the stored alt of EVERY product picture for one language (drift baseline + undo).

    Keys are stringified picture pks (JSON object keys are strings — see module docstring), values
    the raw `alt_text_t9n[language]` or `""`. Missing product collapses to `{"alts": {}}` so the
    bus can still diff; revert treats that empty map as "nothing to restore".
    """
    channel_idx = target_locator["channel"]
    language = target_locator["language"]
    try:
        product = product_service.get_product_by_sku(channel_idx, subject_ref)
    except ObjectDoesNotExist:
        return {"alts": {}}
    return {
        "alts": {
            str(pk): (alt or {}).get(language) or "" for pk, alt in product.pictures.values_list("pk", "alt_text_t9n")
        }
    }


def _write_picture_alts(channel_idx: str, *, subject_ref: str, language: str, alts: dict) -> None:
    """Shared per-picture read-merge-write used by both apply and revert (etap-05-extra).

    Each value lands in `alt_text_t9n[language]` of its picture — sibling languages and pictures
    absent from the map are never touched. All-or-nothing: pks are validated against the product
    BEFORE any write and the whole batch runs in one `transaction.atomic()`, so an unknown/foreign
    pk raises `ValueError` with zero partial writes. `pp.save(update_fields=["alt_text_t9n"])`
    fires post_save → gap recompute + Matrix sync (gated + debounced; no loop risk).
    """
    if not isinstance(alts, dict):
        raise ValueError(f"enrichment_adapter expects an 'alts' dict for picture_alt, got {type(alts).__name__}")
    parsed: dict[int, str] = {}
    for raw_pk, alt in alts.items():
        if not isinstance(alt, str):
            raise ValueError(
                f"enrichment_adapter expects a string alt for picture {raw_pk!r}/{language!r}, got {type(alt).__name__}"
            )
        try:
            parsed[int(raw_pk)] = alt
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid picture_pk {raw_pk!r} in picture_alt 'alts' map") from exc

    product = product_service.get_product_by_sku(channel_idx, subject_ref)
    with transaction.atomic():
        pps = list(ProductPicture.objects.filter(product=product, pk__in=parsed))
        if unknown := sorted(set(parsed) - {pp.pk for pp in pps}):
            raise ValueError(f"unknown picture_pk(s) for product {subject_ref!r}: {unknown}")
        for pp in pps:
            merged = dict(pp.alt_text_t9n or {})
            merged[language] = parsed[pp.pk]
            pp.alt_text_t9n = merged
            pp.save(update_fields=["alt_text_t9n"])


def _read_current_video(subject_ref: str, target_locator: dict) -> dict:
    """Stored names of the product's VIDEO files (drift baseline; revert diffs two of these).

    Names are the hashed storage names — unique per `Files` row (SHA1 dedup), so they identify a
    link. Missing product collapses to `{"files": []}` so the bus can still diff.
    """
    try:
        product = product_service.get_product_by_sku(target_locator["channel"], subject_ref)
    except ObjectDoesNotExist:
        return {"files": []}
    names = ProductFile.objects.filter(product=product, file__file_type=FileRoleEnum.VIDEO).values_list(
        "file__file", flat=True
    )
    return {"files": sorted(names)}


def _apply_video(proposal) -> None:
    """Staged video → `upload_file` (type VIDEO, SHA1 dedup, label = name in the main language) → link."""
    channel_idx = proposal.target_locator["channel"]
    product = product_service.get_product_by_sku(channel_idx, proposal.subject_ref)
    label = product.name_lang(product.shop.default_language.iso2.lower())[:256]
    staged = proposal.open_staged_file()
    try:
        video = product_file_service.upload_file(staged, file_label=label, file_type="video")
    finally:
        staged.close()
    if video.file_type != FileRoleEnum.VIDEO:
        raise ValueError(f"staged video for {proposal.subject_ref!r} deduplicated to a non-VIDEO file")
    product_file_service.link_file_to_product(channel_idx, proposal.subject_ref, video.pk)


def _revert_video(proposal) -> None:
    """Unlink the file(s) this proposal linked: in `applied_snapshot` but not in `current_snapshot`.

    The `Files` row stays (only the link goes), mirroring `product_file_service.unlink_file_from_product`.
    """
    applied = set((proposal.applied_snapshot or {}).get("files") or [])
    added = applied - set((proposal.current_snapshot or {}).get("files") or [])
    if not added:
        raise ValueError(
            f"video revert for {proposal.subject_ref!r}: applied_snapshot adds no file "
            f"(snapshot {proposal.applied_snapshot!r})"
        )
    channel_idx = proposal.target_locator["channel"]
    product = product_service.get_product_by_sku(channel_idx, proposal.subject_ref)
    for link_pk in ProductFile.objects.filter(product=product, file__file__in=added).values_list("pk", flat=True):
        product_file_service.unlink_file_from_product(channel_idx, proposal.subject_ref, link_pk)


def main_picture(*, subject_ref: str, channel: str) -> tuple[bytes, str]:
    """Bytes + mime of the product's main picture (input for the video worker).

    Raises `ObjectDoesNotExist` for a missing product and `ValueError` when there is no main picture
    — the worker fails that subject. Mime is sniffed from the bytes (Picture stores no type).
    """
    picture = product_service.get_product_by_sku(channel, subject_ref).main_picture
    if picture is None or not picture.image:
        raise ValueError(f"product {subject_ref!r} has no main picture in channel {channel!r}")
    return _image_bytes(picture)


def list_pictures(*, subject_ref: str, channel: str) -> list[dict]:
    """`[{ref, label, url, is_main}]` of the product's pictures — main first, then by position — for choosing
    the picture a video animates. `ref` is the product-picture link pk (what `picture` takes); the label is its
    alt text in the channel's main language, else the original file name. A picture linked twice is listed once.

    An unknown product or channel raises `ObjectDoesNotExist`.
    """
    product = product_service.get_product_by_sku(channel, subject_ref)
    main = (product.shop.default_language.iso2.lower(),)
    links = product.pictures.select_related("picture").order_by("position", "pk")
    seen: set[int] = set()
    options = []
    for link in links:
        if link.picture_id in seen or not link.picture.image:
            continue
        seen.add(link.picture_id)
        options.append(_picture_option(link, main))
    return sorted(options, key=lambda option: not option["is_main"])


def _picture_option(link: ProductPicture, langs: tuple[str]) -> dict:
    picture = link.picture
    return {
        "ref": str(link.pk),
        "label": _first_language(link.alt_text_t9n, langs) or picture.original_file_name or "",
        "url": picture.image.url,
        "is_main": link.picture_role == PictureRoleEnum.MAIN,
    }


def picture(*, subject_ref: str, channel: str, picture_ref: str) -> tuple[bytes, str]:
    """Bytes + mime of one of the product's pictures (`ref` from `list_pictures`) — input for the video worker.

    Raises `LookupError` when the ref is not a picture of this product (a foreign or unknown ref is never read),
    `ObjectDoesNotExist` for a missing product.
    """
    product = product_service.get_product_by_sku(channel, subject_ref)
    pk = int(picture_ref) if picture_ref.isdigit() else None
    link = product.pictures.select_related("picture").filter(pk=pk).first() if pk else None
    if link is None or not link.picture.image:
        raise LookupError(f"picture {picture_ref!r} is not a picture of product {subject_ref!r}")
    return _image_bytes(link.picture)


def _image_bytes(picture: Picture) -> tuple[bytes, str]:
    """The stored file's bytes; mime is sniffed from them (Picture stores no type)."""
    with picture.image.open("rb") as fh:
        data = fh.read()
    with Image.open(io.BytesIO(data)) as image:
        return data, Image.MIME.get(image.format, "application/octet-stream")


# Prompt-context caps: keep `build_context` around ~4 KB whatever the catalogue holds.
_CONTEXT_DESCRIPTION_CAP = 1200
_CONTEXT_SHORT_DESCRIPTION_CAP = 300
_CONTEXT_VALUE_CAP = 100
_CONTEXT_MAX_ATTRIBUTES = 20
_CONTEXT_TOP_LEVEL_IDXS = frozenset({"name", "brand", "description", "short_description"})
_NUMERIC_TYPES = frozenset(
    {FeatureTypeEnum.DECIMAL, FeatureTypeEnum.TEMPERATURE, FeatureTypeEnum.LENGTH, FeatureTypeEnum.MASS}
)


def build_context(*, subject_ref: str, channel: str, language: str) -> dict:
    """Compact, JSON-safe product facts for an AI prompt — read-only, constant query count.

    Text values are taken in `language`, falling back to the channel's main language; the name — the
    product's identity, also its label in review — then to any language it has. Long texts are
    stripped of markup, then capped (description, short description, category, every attribute value;
    at most 20 attributes).
    """
    product = product_service.get_product_by_sku(channel, subject_ref)
    langs = (language.lower(), product.shop.default_language.iso2.lower())
    values = _attribute_texts(product, langs)
    attributes = [(idx, text) for idx, text in values.items() if idx not in _CONTEXT_TOP_LEVEL_IDXS]
    return {
        "sku": product.real_product.sku,
        "name": _cap(values.get("name", ""), _CONTEXT_VALUE_CAP),
        "brand": _cap(values.get("brand", ""), _CONTEXT_VALUE_CAP),
        "category": _cap(_category_name(product, langs), _CONTEXT_VALUE_CAP),
        "attributes": {idx: _cap(text, _CONTEXT_VALUE_CAP) for idx, text in attributes[:_CONTEXT_MAX_ATTRIBUTES]},
        "description": _cap(values.get("description", ""), _CONTEXT_DESCRIPTION_CAP),
        "short_description": _cap(values.get("short_description", ""), _CONTEXT_SHORT_DESCRIPTION_CAP),
    }


def _attribute_texts(product, langs: tuple[str, str]) -> dict[str, str]:
    """`{feature_idx: text}` for every non-empty attribute in one query (multiselect rows joined)."""
    rows = (
        ProductAttribute.objects.filter(product=product)
        .select_related("feature", "attribute")
        .order_by("feature__idx", "pk")
    )
    texts: dict[str, list[str]] = {}
    for row in rows:
        if text := _attribute_text(row, langs):
            texts.setdefault(row.feature.idx, []).append(text)
    return {idx: ", ".join(parts) for idx, parts in texts.items()}


def _attribute_text(row: ProductAttribute, langs: tuple[str, str]) -> str:
    """One attribute row as plain text; JSON/datetime/unknown types are skipped ("")."""
    feature_type = row.feature.feature_type
    if feature_type in _T9N_TEXT_TYPES:
        text = _first_language(row.value_txt_t9n, langs)
        if not text and row.feature.idx == SYSTEM_FEATURE_NAME_IDX:
            text = _first_language(row.value_txt_t9n, tuple(row.value_txt_t9n or {}))  # any language beats none
        return text
    if feature_type in (FeatureTypeEnum.SELECT, FeatureTypeEnum.MULTISELECT):
        return _first_language(row.attribute.name_t9n, langs) if row.attribute else ""
    if feature_type in (FeatureTypeEnum.VARCHAR255, FeatureTypeEnum.TEXT):
        return _plain(row.value_txt or "")
    if feature_type == FeatureTypeEnum.BOOL and row.value_bool is not None:
        return "yes" if row.value_bool else "no"
    if feature_type in _NUMERIC_TYPES and row.value_decimal is not None:
        return f"{row.value_decimal.normalize():f}"
    return ""


def _category_name(product, langs: tuple[str, str]) -> str:
    """Name of the product's first category (by position), "" when it has none."""
    link = product.product_in_category.select_related("category").order_by("position", "pk").first()
    return _first_language(link.category.name_t9n, langs) if link else ""


def _first_language(t9n, langs: tuple[str, str]) -> str:
    """First non-blank value of a `{iso2: text}` map in `langs` order, "" if none."""
    if not isinstance(t9n, dict):
        return ""
    for lang in langs:
        if text := _plain(str(t9n.get(lang) or "")):
            return text
    return ""


def _plain(text: str) -> str:
    """Markup and HTML comments stripped, whitespace collapsed — caps then count facts, not tags."""
    return " ".join(strip_tags(text).split())


def _cap(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[: limit - 1].rstrip()}…"


def describe_fields(*, channel: str, language: str = "") -> list[dict]:
    """Writable fields of the catalogue: T9N text (`text`/`html`) and select/multiselect features.

    PIM features are global, so every channel sees the same set. Labels are in `language`, falling
    back to the channel's main language, then the idx. Select fields carry at most 200 options plus
    `options_truncated`. Three queries whatever the catalogue holds: channel, features, options.
    """
    langs = _label_languages(channel, language)
    features = list(
        Feature.objects.filter(feature_type__in=_FIELD_SHAPES)
        .exclude(idx__in=_NON_WRITABLE_IDXS)
        .order_by("display_order", "idx")
    )
    options = _feature_options([f.pk for f in features if f.feature_type in _SELECT_TYPES])
    return [_describe_field(feature, langs, options.get(feature.pk, [])) for feature in features]


def _label_languages(channel_idx: str, language: str) -> tuple[str, str]:
    main = _get_channel(channel_idx).default_language.iso2.lower()
    return (language or main).lower(), main


def _get_channel(channel_idx: str) -> Channel:
    return Channel.objects.select_related("default_language").get(idx=channel_idx)


def _feature_options(feature_ids: list[int]) -> dict[int, list[tuple[str, dict]]]:
    """`{feature_id: [(idx, name_t9n), ...]}` — at most `_MAX_OPTIONS + 1` per feature (one query)."""
    if not feature_ids:
        return {}
    rank = Window(RowNumber(), partition_by=F("feature_id"), order_by=(F("display_order").asc(), F("idx").asc()))
    rows = (
        Attribute.objects.filter(feature_id__in=feature_ids)
        .annotate(rank=rank)
        .filter(rank__lte=_MAX_OPTIONS + 1)
        .order_by("feature_id", "rank")
        .values_list("feature_id", "idx", "name_t9n")
    )
    options: dict[int, list[tuple[str, dict]]] = {}
    for feature_id, idx, name_t9n in rows:
        options.setdefault(feature_id, []).append((idx, name_t9n))
    return options


def _describe_field(feature: Feature, langs: tuple[str, str], options: list[tuple[str, dict]]) -> dict:
    field_type, max_length, translatable = _field_shape(feature)
    field = {
        "key": feature.idx,
        "label": _first_language(feature.name_t9n, langs) or feature.idx,
        "type": field_type,
        "max_length": max_length,
        "translatable": translatable,
    }
    if feature.feature_type in _SELECT_TYPES:
        field["options"] = [
            {"value": idx, "label": _first_language(name_t9n, langs) or idx} for idx, name_t9n in options[:_MAX_OPTIONS]
        ]
        field["options_truncated"] = len(options) > _MAX_OPTIONS
    return field


def _field_shape(feature: Feature) -> tuple[str, int | None, bool]:
    if feature.feature_type in _T9N_TEXT_TYPES and (feature.is_seo or feature.idx in SEO_FEATURE_IDXS):
        return _SEO_TEXT_SHAPE
    return _FIELD_SHAPES[feature.feature_type]


def channel_languages(*, channel: str) -> list[str]:
    """The channel's languages as lowercase iso2, main language first, the rest sorted."""
    record = _get_channel(channel)
    main = record.default_language.iso2.lower()
    others = {iso2.lower() for iso2 in record.languages.values_list("iso2", flat=True)} - {main}
    return [main, *sorted(others)]


def subject_labels(*, refs: list[str], channel: str) -> dict[str, str]:
    """`{sku: name}` of the `refs` that exist in the channel (unknown SKUs are left out) — two queries.

    The name in the channel's main language, else any language it has; "" when the product has no name. An unknown
    channel raises `Channel.DoesNotExist`.
    """
    record = _get_channel(channel)
    skus = dict(Product.objects.filter(shop=record, real_product__sku__in=refs).values_list("pk", "real_product__sku"))
    labels = dict.fromkeys(skus.values(), "")
    names = ProductAttribute.objects.filter(product_id__in=skus, feature__idx=SYSTEM_FEATURE_NAME_IDX)
    main = (record.default_language.iso2.lower(),)
    for product_id, t9n in names.values_list("product_id", "value_txt_t9n"):
        name = _first_language(t9n, main) or _first_language(t9n, tuple(t9n or {}))
        labels[skus[product_id]] = _cap(name, _CONTEXT_VALUE_CAP)
    return labels


def make_locator(*, field_key: str, channel: str, language: str | None) -> dict:
    """`attribute_value` locator for a catalogue field; language is None for select features.

    Raises `ValueError` for an unknown or non-writable field, or a text field without a language.
    """
    if field_key in _NON_WRITABLE_IDXS:
        raise ValueError(f"feature {field_key!r} is not a writable field (system route/SEO field)")
    feature = _get_feature(field_key)
    if feature.feature_type in _SELECT_TYPES:
        return {"channel": channel, "language": None, "feature_idx": field_key}
    if feature.feature_type not in _T9N_TEXT_TYPES:
        raise ValueError(f"feature {field_key!r} is not a writable field (feature_type={feature.feature_type})")
    if not language:
        raise ValueError(f"translatable field {field_key!r} needs a language")
    return {"channel": channel, "language": language.lower(), "feature_idx": field_key}


def field_key(*, locator: dict) -> str | None:
    """Inverse of `make_locator`: the catalog key an `attribute_value` locator points at.

    None for locators without a catalog field (`picture_alt`, `video`) — the bus then revises without
    catalog meta. Without this extra the bus falls back to `locator["field"]`, which PIM locators never carry.
    """
    return locator.get("feature_idx")


def category_of(subject_ref: str, *, channel: str | None = None) -> str | None:
    """Memory ref of the product's first category by `(position, pk)`: `"category:<idx>"`, None without one.

    The prefix keeps the ref apart from SKUs under the same `subject_module`. `channel` narrows to that
    channel's product; without it the first link across every channel carrying the SKU wins.
    """
    links = ProductInCategory.objects.filter(product__real_product__sku=subject_ref)
    if channel:
        links = links.filter(product__shop__idx=channel)
    idx = links.order_by("position", "pk").values_list("category__idx", flat=True).first()
    return f"{_CATEGORY_REF_PREFIX}{idx}" if idx else None


def resolve_targets(scope_spec: dict, page: int = 1) -> list:
    """Resolve a `list` / `filter` / `csv` scope into a page of SKUs (lazy, channel-scoped).

    `list`/`csv` echo the explicit `refs`. `filter` runs `product_service.list_products` and slices
    the page — the QuerySet stays lazy, only the page is materialised.
    """
    mode = scope_spec.get("mode")
    offset = (max(page, 1) - 1) * _PAGE_SIZE
    if mode in ("list", "csv"):
        # Page the explicit refs too — a worker could pass a 500k-SKU list (DoS) otherwise.
        refs = scope_spec.get("refs", [])
        return list(refs[offset : offset + _PAGE_SIZE])
    if mode == "filter":
        channel_idx = scope_spec["channel"]
        filters = {k: v for k, v in (scope_spec.get("filters") or {}).items() if k in _ALLOWED_FILTERS}
        qs = product_service.list_products(channel_idx, **filters)
        return [p.real_product.sku for p in qs[offset : offset + _PAGE_SIZE]]
    raise ValueError(f"unsupported scope mode for pim adapter: {mode!r}")


def find_gaps(check: str, params: dict, scope: dict) -> list[dict]:  # noqa: ARG001 — params reserved by the contract
    """Page of gap candidates for the enrichment bus, read from materialised ``GapFinding`` rows.

    ``check`` = ``GapDefinition.key``. ``params`` is accepted per the cross-module contract but
    unused — PIM's rule parameters live on the ``GapDefinition`` row itself. ``scope`` carries
    ``{"channel": <idx>, "language": <iso2, optional>, "page": <int, injected by the bus>}``.

    Three rules this side owns:
    - **Deep-muted targets are already absent** — a ``GapExemption`` stops detection from ever
      writing the finding, so no extra filtering happens here.
    - **Inherited findings are excluded** — the fix belongs on the source channel; writing on an
      inheriting channel would create unwanted ``overridden_langs`` overrides.
    - **Stable paging** — ordered by ``(product_id, language)`` so the bus's re-pull-page-1
      work-queue contract sees a deterministic front.
    """
    try:
        definition = GapDefinition.objects.get(key=check)
    except GapDefinition.DoesNotExist:
        raise ValueError(f"unknown gap definition key {check!r}") from None
    channel_idx = scope.get("channel")
    if not channel_idx:
        raise ValueError("scope.channel is required for find_gaps")

    page = max(int(scope.get("page", 1)), 1)
    offset = (page - 1) * _PAGE_SIZE

    qs = GapFinding.objects.filter(definition=definition, channel_idx=channel_idx, inherited=False)
    if language := scope.get("language"):
        # Mirror gap_query_service: keep language-neutral findings (NULL) alongside the requested one.
        qs = qs.filter(Q(language=language) | Q(language__isnull=True))
    qs = qs.select_related("product__real_product").order_by("product_id", "language")

    return [_gap_candidate(definition, finding, channel_idx) for finding in qs[offset : offset + _PAGE_SIZE]]


def _gap_candidate(definition: GapDefinition, finding, channel_idx: str) -> dict:
    """One finding → one plain-dict candidate (the bus and the worker treat it as opaque-ish data).

    Shape follows the gaps-per-module pattern: generic columns the bus may read
    (``subject_ref``, ``target_kind``) + the PIM locator only this adapter interprets.
    """
    candidate = {
        "target_module": "pim",
        "target_type": "product",
        "subject_ref": finding.product.real_product.sku,
        "priority": finding.severity,
        "definition_key": definition.key,
    }
    if definition.check_key == GapCheck.PICTURE_PRESENT:
        candidate["target_kind"] = "picture"
        candidate["target_locator"] = {"channel": channel_idx}
    elif definition.check_key == GapCheck.PICTURE_ALT_PRESENT:
        # One language-scoped finding covers ALL pictures missing that alt — the worker fetches
        # the per-picture detail via read_current's {"alts": {pk: alt}} snapshot.
        candidate["target_kind"] = "picture_alt"
        candidate["target_locator"] = {"channel": channel_idx, "language": finding.language}
    elif definition.check_key == GapCheck.FEATURE_SET_DEFAULT:
        # Classification gap — language-neutral (findings carry language=NULL), no feature locator.
        # The shared inherited=False filter is a no-op here: the structural check never emits
        # inherited findings (gap_check_registry.feature_set_default has no inheritance branch).
        candidate["target_kind"] = "feature_set"
        candidate["target_locator"] = {"channel": channel_idx}
    elif definition.check_key == GapCheck.CATEGORY_PRESENT:
        # Classification gap, same shape as feature_set — language-neutral, no feature locator.
        # The AI picks one or more existing categories; apply writes the full set.
        candidate["target_kind"] = "category"
        candidate["target_locator"] = {"channel": channel_idx}
    else:
        candidate["target_kind"] = "attribute_value"
        candidate["target_locator"] = {
            "channel": channel_idx,
            "language": finding.language,
            "feature_idx": (definition.params or {}).get("feature_idx"),
        }
    return candidate

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
- `target_locator`  = `{"channel": <channel_idx>, "language": <iso2>, "feature_idx": <idx>}`  (text)
                    | `{"channel": <channel_idx>}`                                            (picture)
                    | `{"channel": <channel_idx>}`                                            (feature_set)
                    | `{"channel": <channel_idx>, "language": <iso2>}`                        (picture_alt)
- `proposed_value`  = `{"text": <new value for that single language>}`                        (text)
                    | `{"op": "replace_main", "alt_t9n": {<iso2>: <alt>}}`                    (picture)
                    | `{"featureset_idx": <idx of an existing FeatureSet>}`                   (feature_set)
                    | `{"alts": {"<picture_pk>": <alt for that single language>}}`            (picture_alt)
- `current_snapshot`= `{"text": <raw stored value for that language, "" if absent>}`          (text)
                    | `{"sha1", "role", "position", "alt_t9n", "url"}` of the old main, `{}` if none (picture)
                    | `{"featureset_idx": <current idx, "" if product missing>}`              (feature_set)
                    | `{"alts": {"<picture_pk>": <stored alt, "" if absent>}}` of ALL pictures (picture_alt)

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
   marked in `overridden_langs` — but ONLY when inheritance is actually enabled for that flag on a
   non-default channel (decision PO: don't write override metadata where it's meaningless).
"""

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q

from ..models import (
    Feature,
    FeatureSet,
    FeatureTypeEnum,
    GapCheck,
    GapDefinition,
    GapFinding,
    Picture,
    PictureRoleEnum,
    ProductAttribute,
    ProductPicture,
)
from ..settings import DESCRIPTION_FEATURE_IDXS
from . import product_picture_service, product_service

# How many SKUs a worker pulls per `resolve_targets` page. The bus passes `page`; we never
# materialise the whole catalogue.
_PAGE_SIZE = 100

# Only translatable text features are writable through the referential adapter. Media and
# scalar/select features get their own adapters/etaps — fail loud rather than silently no-op
# (a t9n payload sent to a non-t9n feature would be dropped by `_set_product_attributes`).
_T9N_TEXT_TYPES = frozenset({FeatureTypeEnum.VARCHAR255_T9N, FeatureTypeEnum.TEXT_T9N})

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
    if target_kind != "attribute_value":
        return {"text": ""}
    channel_idx, language, feature_idx = _locator(target_locator)
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
    """Write `proposed_value["text"]` into the target feature for one language (text only).

    The ONLY place enrichment writes back to PIM. Drift is already checked by the bus
    (`apply_service.apply`) before we get here. Read-merge-write + inheritance override (see module
    docstring). Raises for unsupported feature types / missing product so misuse is loud.
    """
    if proposal.target_kind == "picture":
        _apply_picture(proposal)
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
    channel_idx, language, feature_idx = _locator(proposal.target_locator)
    _write_text(
        channel_idx,
        subject_ref=proposal.subject_ref,
        feature_idx=feature_idx,
        language=language,
        text=proposal.proposed_value.get("text"),
    )


def revert(proposal) -> None:
    """Restore the target to `current_snapshot` (single-level undo — etap-09 deepens this)."""
    if proposal.target_kind == "picture":
        _revert_picture(proposal)
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
    channel_idx, language, feature_idx = _locator(proposal.target_locator)
    _write_text(
        channel_idx,
        subject_ref=proposal.subject_ref,
        feature_idx=feature_idx,
        language=language,
        text=proposal.current_snapshot.get("text", ""),
    )


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


def _write_text(channel_idx: str, *, subject_ref: str, feature_idx: str, language: str, text) -> None:
    """Shared read-merge-write + override used by both apply and revert.

    `text` must be a plain string — `value_txt_t9n` is a `{lang: str}` map and every reader (get_value,
    Matrix sync, storefront) indexes it as a scalar. Writing a dict/list/None would corrupt the field
    for all consumers, so reject it loudly here rather than silently persisting structured JSON.
    """
    if not isinstance(text, str):
        raise ValueError(
            f"enrichment_adapter expects a string value for {feature_idx!r}/{language!r}, got {type(text).__name__}"
        )

    try:
        feature = Feature.objects.get(idx=feature_idx)
    except Feature.DoesNotExist as exc:
        raise ValueError(f"unknown feature_idx {feature_idx!r}") from exc
    if feature.feature_type not in _T9N_TEXT_TYPES:
        raise ValueError(
            f"enrichment_adapter writes translatable text only; feature {feature_idx!r} is "
            f"feature_type={feature.feature_type} (expected VARCHAR255_T9N or TEXT_T9N)"
        )

    product = product_service.get_product_by_sku(channel_idx, subject_ref)
    existing = ProductAttribute.objects.filter(product=product, feature=feature).first()
    merged = dict(existing.value_txt_t9n or {}) if existing is not None else {}
    merged[language] = text

    product_service.update_product(
        channel_idx, subject_ref, attributes=[{"feature_idx": feature_idx, "value_txt_t9n": merged}]
    )

    _mark_overridden_if_inheriting(product, feature, language)


def _mark_overridden_if_inheriting(product, feature: Feature, language: str) -> None:
    """Mark the language overridden so materialisation won't clobber it — only where it matters.

    No-op on the default channel (it's the inheritance source) or when the product does not inherit
    the relevant flag (description vs attribute). The attribute was deleted+recreated by the write, so
    we re-fetch it and set `overridden_langs` directly rather than going through
    `toggle_language_override` (which raises unless inheritance is enabled and the attribute exists).
    """
    if product.shop.is_default:
        return
    inherits = product.inherit_descriptions if feature.idx in DESCRIPTION_FEATURE_IDXS else product.inherit_attributes
    if not inherits:
        return
    attr = ProductAttribute.objects.filter(product=product, feature=feature).first()
    if attr is None:
        return
    overridden = set(attr.overridden_langs or [])
    if language in overridden:
        return
    overridden.add(language)
    attr.overridden_langs = sorted(overridden)
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

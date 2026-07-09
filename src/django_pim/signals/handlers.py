# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from django_pim import settings as pim_settings
from django_pim.models import (
    Attribute,
    Feature,
    GapDefinition,
    GapFinding,
    Product,
    ProductAttribute,
    ProductFile,
    ProductInCategory,
    ProductPicture,
    ProductVideo,
    RealProduct,
)
from django_pim.signals.dispatch import enqueue_gap_recompute, enqueue_product_sync
from django_pim.signals.killswitch import is_gaps_enabled, is_matrix_signals_enabled, is_matrix_sync_suppressed

logger = logging.getLogger("django_pim.signals")


def _should_skip(channel_idx: str | None = None, raw: bool = False) -> bool:
    """Common guard checks for all signal handlers."""
    if raw:
        return True
    if is_matrix_sync_suppressed():
        return True
    if not is_matrix_signals_enabled():
        return True
    if channel_idx and channel_idx in pim_settings.PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST:
        return True
    return False


def _enqueue_for_product(product: Product) -> None:
    """Enqueue sync for a single Product instance."""
    try:
        sku = product.real_product.sku
        channel_idx = product.shop.idx
    except Exception:
        logger.warning("Could not resolve SKU/channel for Product pk=%s", product.pk)
        return
    if channel_idx in pim_settings.PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST:
        return
    try:
        enqueue_product_sync(sku, channel_idx)
    except Exception:
        logger.warning("Failed to enqueue sync for SKU=%s channel=%s", sku, channel_idx, exc_info=True)


# ─── Product ──────────────────────────────────────────────────────────


@receiver(post_save, sender=Product, dispatch_uid="pim_product_post_save_matrix")
def product_post_save(sender, instance, created, raw, **kwargs):
    if _should_skip(raw=raw):
        return
    _enqueue_for_product(instance)


@receiver(post_delete, sender=Product, dispatch_uid="pim_product_post_delete_matrix")
def product_post_delete(sender, instance, **kwargs):
    if _should_skip():
        return
    _enqueue_for_product(instance)


# ─── ProductAttribute ────────────────────────────────────────────────


@receiver(post_save, sender=ProductAttribute, dispatch_uid="pim_prodattr_post_save_matrix")
def product_attribute_post_save(sender, instance, created, raw, **kwargs):
    if _should_skip(raw=raw):
        return
    try:
        _enqueue_for_product(instance.product)
    except Exception:
        logger.warning("Could not resolve product for ProductAttribute pk=%s", instance.pk)


@receiver(post_delete, sender=ProductAttribute, dispatch_uid="pim_prodattr_post_delete_matrix")
def product_attribute_post_delete(sender, instance, **kwargs):
    if _should_skip():
        return
    try:
        _enqueue_for_product(instance.product)
    except Exception:
        logger.warning("Could not resolve product for ProductAttribute pk=%s", instance.pk)


# ─── RealProduct ──────────────────────────────────────────────────────


@receiver(post_save, sender=RealProduct, dispatch_uid="pim_realproduct_post_save_matrix")
def real_product_post_save(sender, instance, created, raw, **kwargs):
    if _should_skip(raw=raw):
        return
    products = Product.objects.filter(real_product=instance).select_related("shop")
    for product in products:
        _enqueue_for_product(product)


# ─── Attribute (cascade) ─────────────────────────────────────────────


@receiver(post_save, sender=Attribute, dispatch_uid="pim_attribute_post_save_matrix")
def attribute_post_save(sender, instance, created, raw, **kwargs):
    if _should_skip(raw=raw):
        return
    affected = (
        Product.objects.filter(products_attributes__attribute=instance)
        .select_related("real_product", "shop")
        .distinct()
    )

    if affected.count() > pim_settings.PIM_MATRIX_SIGNALS_BATCH_THRESHOLD:
        _enqueue_channel_rebuilds(affected)
    else:
        for product in affected:
            _enqueue_for_product(product)


# ─── Feature (cascade) ───────────────────────────────────────────────


@receiver(post_save, sender=Feature, dispatch_uid="pim_feature_post_save_matrix")
def feature_post_save(sender, instance, created, raw, **kwargs):
    if _should_skip(raw=raw):
        return
    affected = (
        Product.objects.filter(feature_set__feature_in_feature_set__feature=instance)
        .select_related("real_product", "shop")
        .distinct()
    )

    if affected.count() > pim_settings.PIM_MATRIX_SIGNALS_BATCH_THRESHOLD:
        _enqueue_channel_rebuilds(affected)
    else:
        for product in affected:
            _enqueue_for_product(product)


# ─── ProductPicture ───────────────────────────────────────────────────


@receiver(post_save, sender=ProductPicture, dispatch_uid="pim_prodpic_post_save_matrix")
def product_picture_post_save(sender, instance, created, raw, **kwargs):
    if raw:
        return
    _propagate_media_if_default(instance.product)
    if _should_skip(raw=raw):
        return
    try:
        _enqueue_for_product(instance.product)
    except Exception:
        logger.warning("Could not resolve product for ProductPicture pk=%s", instance.pk)


@receiver(post_delete, sender=ProductPicture, dispatch_uid="pim_prodpic_post_delete_matrix")
def product_picture_post_delete(sender, instance, **kwargs):
    _propagate_media_if_default(instance.product)
    if _should_skip():
        return
    try:
        _enqueue_for_product(instance.product)
    except Exception:
        logger.warning("Could not resolve product for ProductPicture pk=%s", instance.pk)


# ─── ProductVideo ─────────────────────────────────────────────────────


@receiver(post_save, sender=ProductVideo, dispatch_uid="pim_prodvid_post_save_matrix")
def product_video_post_save(sender, instance, created, raw, **kwargs):
    if raw:
        return
    _propagate_media_if_default(instance.product)
    if _should_skip(raw=raw):
        return
    try:
        _enqueue_for_product(instance.product)
    except Exception:
        logger.warning("Could not resolve product for ProductVideo pk=%s", instance.pk)


@receiver(post_delete, sender=ProductVideo, dispatch_uid="pim_prodvid_post_delete_matrix")
def product_video_post_delete(sender, instance, **kwargs):
    _propagate_media_if_default(instance.product)
    if _should_skip():
        return
    try:
        _enqueue_for_product(instance.product)
    except Exception:
        logger.warning("Could not resolve product for ProductVideo pk=%s", instance.pk)


# ─── ProductInCategory ────────────────────────────────────────────────


@receiver(post_save, sender=ProductInCategory, dispatch_uid="pim_prodcat_post_save_matrix")
def product_in_category_post_save(sender, instance, created, raw, **kwargs):
    if _should_skip(raw=raw):
        return
    try:
        _enqueue_for_product(instance.product)
    except Exception:
        logger.warning("Could not resolve product for ProductInCategory pk=%s", instance.pk)


@receiver(post_delete, sender=ProductInCategory, dispatch_uid="pim_prodcat_post_delete_matrix")
def product_in_category_post_delete(sender, instance, **kwargs):
    if _should_skip():
        return
    try:
        _enqueue_for_product(instance.product)
    except Exception:
        logger.warning("Could not resolve product for ProductInCategory pk=%s", instance.pk)


# ─── ProductFile (inheritance propagation) ────────────────────────────


@receiver(post_save, sender=ProductFile, dispatch_uid="pim_prodfile_post_save_matrix")
def product_file_post_save(sender, instance, created, raw, **kwargs):
    if raw:
        return
    _propagate_media_if_default(instance.product)


@receiver(post_delete, sender=ProductFile, dispatch_uid="pim_prodfile_post_delete_matrix")
def product_file_post_delete(sender, instance, **kwargs):
    _propagate_media_if_default(instance.product)


# ─── Helpers ──────────────────────────────────────────────────────────


def _propagate_media_if_default(product: Product) -> None:
    """Propagate media changes from default channel to inheriting products."""
    try:
        if not product.shop.is_default:
            return
    except Exception:
        return
    try:
        from django_pim.services.inheritance_service import propagate_media_to_inheriting

        propagate_media_to_inheriting(product)
    except Exception:
        logger.warning("Failed to propagate media for Product pk=%s", product.pk, exc_info=True)


def _enqueue_channel_rebuilds(products_qs) -> None:
    """For large cascades, enqueue full channel rebuilds instead of per-product."""
    channel_idxs = set(products_qs.values_list("shop__idx", flat=True).distinct())
    for channel_idx in channel_idxs:
        if channel_idx in pim_settings.PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST:
            continue
        enqueue_product_sync("__CHANNEL_REBUILD__", channel_idx)
        logger.info("Cascade threshold exceeded, enqueued channel rebuild for channel=%s", channel_idx)


# ══════════════════════════════════════════════════════════════════════════
# Quality-gaps recompute (etap-03)
#
# A SEPARATE tor from Matrix sync above: own gate (is_gaps_enabled, independent of
# is_matrix_signals_enabled), own debounce keys/flush task (enqueue_gap_recompute). These handlers
# never call is_matrix_signals_enabled() — the highlighter recomputes even with Matrix sync off.
# Bulk imports still wrap in suppress_matrix_signals(); gaps honour that to avoid per-row lawina.
# ══════════════════════════════════════════════════════════════════════════


def _should_skip_gaps(raw: bool = False) -> bool:
    return raw or is_matrix_sync_suppressed() or not is_gaps_enabled()


def _enqueue_gap(product_pk: int) -> None:
    try:
        enqueue_gap_recompute(product_pk)
    except Exception:
        logger.warning("Failed to enqueue gap recompute for Product pk=%s", product_pk, exc_info=True)


def _gap_for_related(instance) -> None:
    """Enqueue a gap recompute for the product owning a related row (attribute/picture/...)."""
    try:
        _enqueue_gap(instance.product_id)
    except Exception:
        logger.warning("Could not resolve product for %s pk=%s", type(instance).__name__, instance.pk)


# ─── Product data on-save / on-delete ─────────────────────────────────────


@receiver(post_save, sender=Product, dispatch_uid="pim_product_post_save_gaps")
def product_post_save_gaps(sender, instance, created, raw, **kwargs):
    if _should_skip_gaps(raw=raw):
        return
    _enqueue_gap(instance.pk)


@receiver(post_save, sender=ProductAttribute, dispatch_uid="pim_prodattr_post_save_gaps")
def product_attribute_post_save_gaps(sender, instance, created, raw, **kwargs):
    if _should_skip_gaps(raw=raw):
        return
    _gap_for_related(instance)


@receiver(post_delete, sender=ProductAttribute, dispatch_uid="pim_prodattr_post_delete_gaps")
def product_attribute_post_delete_gaps(sender, instance, **kwargs):
    if _should_skip_gaps():
        return
    _gap_for_related(instance)


@receiver(post_save, sender=ProductPicture, dispatch_uid="pim_prodpic_post_save_gaps")
def product_picture_post_save_gaps(sender, instance, created, raw, **kwargs):
    if _should_skip_gaps(raw=raw):
        return
    _gap_for_related(instance)


@receiver(post_delete, sender=ProductPicture, dispatch_uid="pim_prodpic_post_delete_gaps")
def product_picture_post_delete_gaps(sender, instance, **kwargs):
    if _should_skip_gaps():
        return
    _gap_for_related(instance)


@receiver(post_save, sender=ProductVideo, dispatch_uid="pim_prodvid_post_save_gaps")
def product_video_post_save_gaps(sender, instance, created, raw, **kwargs):
    if _should_skip_gaps(raw=raw):
        return
    _gap_for_related(instance)


@receiver(post_delete, sender=ProductVideo, dispatch_uid="pim_prodvid_post_delete_gaps")
def product_video_post_delete_gaps(sender, instance, **kwargs):
    if _should_skip_gaps():
        return
    _gap_for_related(instance)


@receiver(post_save, sender=ProductInCategory, dispatch_uid="pim_prodcat_post_save_gaps")
def product_in_category_post_save_gaps(sender, instance, created, raw, **kwargs):
    if _should_skip_gaps(raw=raw):
        return
    _gap_for_related(instance)


@receiver(post_delete, sender=ProductInCategory, dispatch_uid="pim_prodcat_post_delete_gaps")
def product_in_category_post_delete_gaps(sender, instance, **kwargs):
    if _should_skip_gaps():
        return
    _gap_for_related(instance)


# ─── Feature cascade (feature_type / inheritance flags affect checks) ──────


@receiver(post_save, sender=Feature, dispatch_uid="pim_feature_post_save_gaps")
def feature_post_save_gaps(sender, instance, created, raw, **kwargs):
    if _should_skip_gaps(raw=raw):
        return
    affected = Product.objects.filter(feature_set__feature_in_feature_set__feature=instance).distinct()
    if affected.count() > pim_settings.PIM_MATRIX_SIGNALS_BATCH_THRESHOLD:
        # Wide change = expensive → mark stale (CMS alert + nightly safeguard), do NOT stampede.
        from django_pim.services import gap_rule_service

        gap_rule_service.mark_rules_changed()
        logger.info("Feature cascade exceeded gap threshold — catalogue marked stale (feature=%s)", instance.pk)
    else:
        for pk in affected.values_list("pk", flat=True):
            _enqueue_gap(pk)


# ─── GapDefinition lifecycle (fast path vs mark-stale) ────────────────────


@receiver(pre_save, sender=GapDefinition, dispatch_uid="pim_gapdef_pre_save_gaps")
def gap_definition_pre_save(sender, instance, raw, **kwargs):
    """Snapshot the old row so post_save can tell a severity-only edit from a condition change."""
    if raw or not instance.pk:
        instance._gaps_old = None
        return
    try:
        old = GapDefinition.objects.get(pk=instance.pk)
    except GapDefinition.DoesNotExist:
        instance._gaps_old = None
        return
    instance._gaps_old = {
        "severity": old.severity,
        "active": old.active,
        "signature": (old.check_key, old.params, old.languages, old.channels),
    }


@receiver(post_save, sender=GapDefinition, dispatch_uid="pim_gapdef_post_save_gaps")
def gap_definition_post_save(sender, instance, created, raw, **kwargs):
    if raw or not is_gaps_enabled():
        return
    from django_pim.services import gap_rule_service

    if created:
        gap_rule_service.mark_rules_changed()
        return

    old = getattr(instance, "_gaps_old", None)
    instance._gaps_old = None  # consume the snapshot so a re-save in the same request re-snapshots
    if old is None:
        gap_rule_service.mark_rules_changed()
        return

    signature_now = (instance.check_key, instance.params, instance.languages, instance.channels)
    signature_changed = old["signature"] != signature_now
    active_changed = old["active"] != instance.active
    severity_changed = old["severity"] != instance.severity

    if signature_changed or active_changed:
        if not instance.active:
            gap_rule_service.cleanup_rule_findings(instance)  # disabled → drop its findings + fix rollups
        gap_rule_service.mark_rules_changed()
    elif severity_changed:
        gap_rule_service.apply_severity_change(instance)  # fast path — no catalogue re-detection


@receiver(pre_delete, sender=GapDefinition, dispatch_uid="pim_gapdef_pre_delete_gaps")
def gap_definition_pre_delete(sender, instance, **kwargs):
    """Capture affected products before CASCADE removes the findings, so we can repair rollups."""
    instance._gaps_affected_pks = list(
        GapFinding.objects.filter(definition=instance).values_list("product_id", flat=True).distinct()
    )


@receiver(post_delete, sender=GapDefinition, dispatch_uid="pim_gapdef_post_delete_gaps")
def gap_definition_post_delete(sender, instance, **kwargs):
    if not is_gaps_enabled():
        return
    pks = getattr(instance, "_gaps_affected_pks", [])
    if pks:
        from django_pim.services import gap_recompute_service

        gap_recompute_service.recompute_rollup_for_products(pks)

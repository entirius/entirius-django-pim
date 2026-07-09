# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Celery tasks for PIM inheritance propagation."""

import logging

from django_pim.models import Product

logger = logging.getLogger(__name__)

try:
    from celery import shared_task

    @shared_task(bind=True, max_retries=3, default_retry_delay=10)
    def propagate_inheritance_task(self, product_pk: int, updated_feature_idxs: list[str] | None = None):
        """Async propagation of default channel values to inheriting products.

        Called after updating a product on the default channel when inheriting
        products exist. Processes synchronously within the task (batch of all
        inheriting products for this SKU).

        Args:
            product_pk: PK of the product on the default channel that was updated.
            updated_feature_idxs: Optional list of feature idxs that were updated.
        """
        from django_pim.services.inheritance_service import propagate_to_inheriting_products

        try:
            product = Product.objects.select_related("real_product", "shop", "feature_set").get(pk=product_pk)
        except Product.DoesNotExist:
            logger.warning("propagate_inheritance_task: Product pk=%s not found", product_pk)
            return

        if not product.shop.is_default:
            logger.warning("propagate_inheritance_task: Product pk=%s is not on default channel, skipping", product_pk)
            return

        count = propagate_to_inheriting_products(product, updated_feature_idxs)
        logger.info("propagate_inheritance_task: Propagated to %d products for SKU=%s", count, product.sku)

    # Backward-compatible alias
    propagate_translations_task = propagate_inheritance_task

except ImportError:
    # Celery not installed — provide a no-op fallback
    def propagate_inheritance_task(product_pk: int, updated_feature_idxs: list[str] | None = None):
        """Fallback when Celery is not available — runs synchronously."""
        from django_pim.services.inheritance_service import propagate_to_inheriting_products

        product = Product.objects.select_related("real_product", "shop", "feature_set").get(pk=product_pk)
        propagate_to_inheriting_products(product, updated_feature_idxs)

    propagate_translations_task = propagate_inheritance_task

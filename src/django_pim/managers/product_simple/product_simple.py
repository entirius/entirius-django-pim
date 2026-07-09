# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from ...models import ProductSimple

logger = logging.getLogger(__name__)


class ProductSimpleManager:
    def get(sku_internal=None, ean=None):
        if ean is not None:
            return ProductSimple.objects.filter(ean=ean).first()
        if sku_internal is not None:
            return ProductSimple.objects.filter(sku_internal=sku_internal).first()
        raise Exception("ProductSimpleManager.get(): sku_internal or ean must be set")

    def get_or_create(sku_internal, feature_set=None):
        product = ProductSimpleManager.get(sku_internal=sku_internal)
        if product is None:
            product = ProductSimple(sku_internal=sku_internal, feature_set=feature_set)
            product.save()
            logger.info("New ProductSimple: [%s]", sku_internal)
            created = True
        else:
            created = False
        return (product, created)

    def update_product_quantity(product, quantity=None):
        updated = []
        to_save = False
        if quantity is not None and product.quantity != quantity:
            updated.append("quantity")
            logger.info(f"Product [%s] updated quantity: {product.sku_internal} => {product.quantity}")
            product.quantity = quantity
            to_save = True
        if to_save:
            product.save(update_fields=updated)

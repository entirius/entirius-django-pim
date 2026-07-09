# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from ...models import ProductConfigurable

logger = logging.getLogger(__name__)


class ProductConfigurableManager:
    def get(sku_internal=None, ean=None):
        if ean is not None:
            return ProductConfigurable.objects.filter(ean=ean).first()
        if sku_internal is not None:
            return ProductConfigurable.objects.filter(sku_internal=sku_internal).first()
        raise Exception("ProductConfigurableManager.get(): sku_internal or ean must be set")

    def get_or_create(sku_internal, feature_set=None):
        product = ProductConfigurableManager.get(sku_internal=sku_internal)
        if product is None:
            product = ProductConfigurable(sku_internal=sku_internal, feature_set=feature_set)
            product.save()
            logger.info("New ProductConfigurable: [%s]", sku_internal)
            created = True
        else:
            created = False
        return (product, created)

    def get_subproducts(product_configurable):
        subproducts = []
        for subproduct_link in product_configurable.subproduct_links.all():
            subproducts.append(subproduct_link.subproduct)
        return subproducts

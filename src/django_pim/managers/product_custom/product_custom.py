# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from ...models import ProductCustom

logger = logging.getLogger(__name__)


class ProductCustomManager:
    def get(sku_internal=None, ean=None):
        if ean is not None:
            return ProductCustom.objects.filter(ean=ean).first()
        if sku_internal is not None:
            return ProductCustom.objects.filter(sku_internal=sku_internal).first()
        raise Exception("ProductCustomManager.get(): sku_internal or ean must be set")

    def get_or_create(sku_internal, feature_set=None):
        product = ProductCustomManager.get(sku_internal=sku_internal)
        if product is None:
            product = ProductCustom(sku_internal=sku_internal, feature_set=feature_set)
            product.save()
            logger.info("New ProductCustom: [%s]", sku_internal)
            created = True
        else:
            created = False
        return (product, created)

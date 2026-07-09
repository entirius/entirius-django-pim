# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import hashlib
import logging
import re

from django.db.models import DecimalField, OuterRef, Subquery

from ..models import Feature, Product
from ..models.feature import FeatureScopeEnum
from ..models.product_attribute import ProductAttribute
from ..settings import SYSTEM_FEATURE_VOLUME_IDX

logger = logging.getLogger(__name__)


# django-checkout
def get_volumes_by_sku(channel_idx: str, sku_list: list[str]) -> dict[str, "Decimal | None"]:
    """Return {sku: volume_decimal} for given SKUs in a channel. Volume comes from the system 'volume' feature."""
    volume_subquery = ProductAttribute.objects.filter(
        product=OuterRef("pk"),
        feature__idx=SYSTEM_FEATURE_VOLUME_IDX,
        feature__scope=FeatureScopeEnum.SYSTEM,
    ).values("value_decimal")[:1]

    data = (
        Product.objects.filter(shop__idx=channel_idx, real_product__sku__in=sku_list)
        .annotate(volume=Subquery(volume_subquery, output_field=DecimalField()))
        .values("real_product__sku", "volume")
    )

    return {item["real_product__sku"]: item["volume"] for item in data}


class ProductManager:
    def set_sell_status(products_ids, sell_status):
        if len(products_ids) > 0:
            Product.objects.filter(id__in=products_ids).update(sell_status=sell_status)

    def get_product_features(product):
        features = Feature.objects.filter(
            features_to_sets__is_enabled=True, features_to_sets__products_attributes__product=product
        ).order_by("idx")
        return list(set(list(features)))

    def generate_short_description(product, lang=None):
        desc = product.desc_lang(lang=lang)
        if desc is None or len(desc) == 0:
            return ""
        product_desc = desc[0].upper() + desc[1:]
        # usuwam kropki
        product_desc = product_desc.replace(".", "")
        # usuwam wiecej niz 1 spacje
        product_desc = re.sub(" +", " ", product_desc)
        return product_desc

    def get_or_create(sku_internal, feature_set=None):
        raise Exception("Use ProductConfigurableManager.get_or_create() or ProductSimpleManager.get_or_create()")

    def update_product(product, is_enabled=None, ean=None, name_t9n=None, desc_t9n=None, visibility=None):
        updated = []
        to_save = False
        if is_enabled is not None and product.is_enabled != is_enabled:
            updated.append("is_enabled")
            product.is_enabled = is_enabled
            to_save = True
        if ean is not None and product.ean != ean:
            updated.append("ean")
            product.ean = ean
            to_save = True
        if name_t9n is not None and product.name_t9n != name_t9n:
            orig = product.name_t9n.copy()
            product.name_t9n.update(name_t9n)
            if product.name_t9n != orig:
                updated.append("name_t9n")
                to_save = True
        if desc_t9n is not None and product.desc_t9n != desc_t9n:
            orig = product.desc_t9n.copy()
            product.desc_t9n.update(desc_t9n)
            if product.desc_t9n != orig:
                updated.append("desc_t9n")
                to_save = True
        if visibility is not None and product.visibility != visibility:
            product.visibility = visibility
            updated.append("visibility")
            to_save = True
        if to_save:
            product.save(update_fields=updated)
            logger.info("Product [%s] updated fields: (%s)", product.sku_internal, ", ".join(updated))

    def generate_sku_internal(provider, sku_provider):
        provider_h = provider.sku_prefix
        product_m = hashlib.md5()
        product_m.update(str(sku_provider).encode("UTF-8"))
        product_h = product_m.hexdigest()
        return "%s-%s-%s" % (provider_h[:4], product_h[:4], product_h[4:8])

    def delete(sku_internal, msg=None):
        if msg is None:
            msg = ""
        product = Product.objects.filter(sku_internal=sku_internal).first()
        if product is not None:
            logger.info(f"Delete [{sku_internal}] {msg}")
            product.delete()

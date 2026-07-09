# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from decimal import Decimal

from django_pim.settings import SYSTEM_FEATURE_MAX_LIMIT_BUNDLE_IDX, SYSTEM_FEATURE_MIN_LIMIT_BUNDLE_IDX

from ..product import Product, ProductClassEnum


class ProductBundle(Product):
    def save(self, *args, **kwargs):
        # save what kind we are.
        self.product_class = ProductClassEnum.ProductBundle
        super().save(*args, **kwargs)

    def return_all_subproduct_for_bundle(self):
        return self.bundle_sub_links.all()

    # django-checkout _fetch_bundle_limits
    def get_max_limit_bundle(self) -> Decimal | None:
        pa = self.products_attributes.filter(feature__idx=SYSTEM_FEATURE_MAX_LIMIT_BUNDLE_IDX).first()
        if pa is None:
            return None
        return pa.get_value()

    # django-checkout _fetch_bundle_limits
    def get_min_limit_bundle(self) -> Decimal | None:
        pa = self.products_attributes.filter(feature__idx=SYSTEM_FEATURE_MIN_LIMIT_BUNDLE_IDX).first()
        if pa is None:
            return None
        return pa.get_value()

    class Meta:
        verbose_name_plural = "products bundle"

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from ..product import Product, ProductClassEnum


class ProductConfigurable(Product):
    def save(self, *args, **kwargs):
        # save what kind we are.
        self.product_class = ProductClassEnum.ProductConfigurable
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "products configurable"

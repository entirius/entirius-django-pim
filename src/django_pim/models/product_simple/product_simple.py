# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models

from ..product import Product, ProductClassEnum


class ProductSimple(Product):
    quantity = models.PositiveIntegerField(blank=False, null=False, default=0)

    def save(self, *args, **kwargs):
        # save what kind we are.
        self.product_class = ProductClassEnum.ProductSimple
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "products simple"

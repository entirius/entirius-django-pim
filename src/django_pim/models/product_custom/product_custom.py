# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models

from ..product import Product, ProductClassEnum


class ProductCustom(Product):
    customization_feature_set = models.ForeignKey("FeatureSet", on_delete=models.CASCADE, null=True, blank=True)
    source_product = models.ForeignKey(
        "Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custom_products",
        help_text="Source Simple or Configurable product this custom product is derived from.",
    )

    def save(self, *args, **kwargs):
        # save what kind we are.
        self.product_class = ProductClassEnum.ProductCustom
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "products custom"

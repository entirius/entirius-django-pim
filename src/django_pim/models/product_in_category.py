# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models
from django.utils import timezone


class ProductInCategory(models.Model):
    product = models.ForeignKey(
        "Product",
        related_name="product_in_category",
        verbose_name="product",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )

    category = models.ForeignKey(
        "ProductCategory",
        related_name="product_in_category",
        verbose_name="category",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )

    position = models.IntegerField(null=True, blank=True, default=0)
    updated_at = models.DateTimeField(null=True, blank=True, default=None)

    class Meta:
        verbose_name_plural = "products in categories"
        constraints = [models.UniqueConstraint(fields=["product", "category"], name="unique_product_category")]

    def __str__(self):
        return f"{self.product} - {self.category}"

    def save(self, *args, **kwargs):
        if self.updated_at is None:
            self.updated_at = timezone.now()
        super().save(*args, **kwargs)

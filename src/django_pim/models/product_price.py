# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import datetime

import pytz
from django.db import models


class ProductPrice(models.Model):
    product = models.ForeignKey(
        "Product",
        related_name="product_prices",
        verbose_name="product",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )

    currency = models.ForeignKey(
        "django_regional.Currency",
        related_name="product_prices",
        verbose_name="currency",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    price_brutto = models.DecimalField(blank=True, null=True, max_digits=12, decimal_places=2)
    special_price = models.DecimalField(blank=True, null=True, max_digits=12, decimal_places=2)
    special_price_from = models.DateTimeField(blank=True, null=True)
    special_price_to = models.DateTimeField(blank=True, null=True)

    @property
    def special_price_active(self):
        utc = pytz.UTC
        from_cond = self.special_price_from is None or datetime.datetime.now().replace(
            tzinfo=utc
        ) > self.special_price_from.replace(tzinfo=utc)
        to_cond = self.special_price_to is None or datetime.datetime.now().replace(
            tzinfo=utc
        ) < self.special_price_to.replace(tzinfo=utc)
        return self.special_price is not None and from_cond and to_cond

    def __str__(self):
        return "%s %s %s" % (self.product, self.price_brutto, self.currency)

    class Meta:
        ordering = ["id"]
        verbose_name_plural = "products prices"
        unique_together = ("product", "currency")

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models


class ConfigurableLink(models.Model):
    product_configurable = models.ForeignKey(
        "ProductConfigurable",
        related_name="subproduct_links",
        verbose_name="product_configurable",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )

    subproduct_attribute = models.ForeignKey(
        "ProductAttribute",
        related_name="configurable_links",
        verbose_name="subproduct_attribute",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )

    subproduct = models.ForeignKey(
        "Product",
        related_name="configurable_links",
        verbose_name="subproduct",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )
    objects = models.Manager()

    def __str__(self):
        return "%s %s" % (self.product_configurable, self.subproduct_attribute)

    class Meta:
        ordering = []
        verbose_name_plural = "configurable links"
        unique_together = (("product_configurable", "subproduct_attribute"),)

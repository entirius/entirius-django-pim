# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from enum import IntEnum

from django.db import models
from int_enum_choices import IntEnumChoices

from .product_link_type import ProductLinkType  # noqa: F401  back-compat re-export


class ProductLinkTypeEnum(IntEnum):
    """Legacy enum kept for backward compatibility with managers/importers."""

    UNKNOWN = 0
    RELATED = 1
    CROSSSELL = 2
    UPSELL = 3
    NAVIGATION = 4


class ProductLinkTypeChoices(IntEnumChoices):
    """Legacy choices kept for backward compatibility."""

    enumClass = ProductLinkTypeEnum
    labels = {
        ProductLinkTypeEnum.UNKNOWN: "Unknown",
        ProductLinkTypeEnum.RELATED: "Related",
        ProductLinkTypeEnum.CROSSSELL: "Crosssell",
        ProductLinkTypeEnum.UPSELL: "Upsell",
        ProductLinkTypeEnum.NAVIGATION: "Navigation",
    }


class ProductLink(models.Model):
    product = models.ForeignKey(
        "Product",
        related_name="product_links",
        verbose_name="product",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )
    linked_product = models.ForeignKey(
        "Product",
        related_name="linked_products_links",
        verbose_name="linked_product",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )
    link_type = models.ForeignKey(
        "ProductLinkType",
        related_name="product_links",
        verbose_name="link type",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    position = models.IntegerField(blank=True, null=False, default=1)
    db_created = models.DateTimeField(auto_now_add=True)
    db_modified = models.DateTimeField(auto_now=True)

    @property
    def link_type_name(self):
        return self.link_type.idx if self.link_type else "unknown"

    def __str__(self):
        return f"{self.product.id} - {self.linked_product.id}"

    class Meta:
        ordering = []
        verbose_name_plural = "Products links"
        unique_together = ("product", "linked_product", "link_type")

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models

from .product_picture import PictureRole


class ProductCategoryPicture(models.Model):
    product_category = models.ForeignKey(
        "ProductCategory",
        related_name="pictures",
        verbose_name="product_category",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )
    picture = models.ForeignKey(
        "Picture",
        related_name="product_categories",
        verbose_name="picture",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )
    picture_role = models.PositiveSmallIntegerField(
        choices=PictureRole.choices(), blank=False, null=False, default=PictureRole.enumClass.UNKNOWN
    )

    position = models.IntegerField(default=0, blank=True, null=True)

    class Meta:
        ordering = []
        verbose_name_plural = "product category pictures"
        unique_together = ("product_category", "picture")

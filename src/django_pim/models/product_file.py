# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models


class ProductFile(models.Model):
    product = models.ForeignKey(
        "Product", related_name="products", verbose_name="product", null=False, blank=False, on_delete=models.CASCADE
    )

    file = models.ForeignKey(
        "Files", related_name="files", verbose_name="file", null=False, blank=False, on_delete=models.CASCADE
    )
    is_inherited = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.product}-{self.file.original_file_name}"

    class Meta:
        ordering = []
        verbose_name = "Product File"
        verbose_name_plural = "Product Files"
        unique_together = ("product", "file")

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models


class ProductLinkType(models.Model):
    idx = models.CharField(max_length=64, unique=True)
    name_t9n = models.JSONField(default=dict)
    desc = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Internal description / instruction. Used to ground AI workflows when matching "
            "(feature-set selection, attribute fill). Not shown on the storefront."
        ),
    )
    position = models.IntegerField(default=0)
    db_created = models.DateTimeField(auto_now_add=True)
    db_modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.idx

    class Meta:
        ordering = ["position", "idx"]
        verbose_name = "Product Link Type"
        verbose_name_plural = "Product Link Types"

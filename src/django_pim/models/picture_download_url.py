# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models


class PictureDownloadUrl(models.Model):
    picture = models.ForeignKey(
        "Picture",
        related_name="downloads_urls",
        verbose_name="picture",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    url = models.CharField(db_index=True, max_length=384, blank=False, null=False, unique=True)
    db_created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.url

    class Meta:
        ordering = ["url"]
        verbose_name_plural = "pictures downloads urls"

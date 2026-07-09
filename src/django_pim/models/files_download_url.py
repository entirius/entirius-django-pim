# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models


class FilesDownloadUrl(models.Model):
    file = models.ForeignKey(
        "Files",
        related_name="doc_downloads_urls",
        verbose_name="doc_downloads_urls",
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
        verbose_name = "File downloads urls"
        verbose_name_plural = "File downloads urls"

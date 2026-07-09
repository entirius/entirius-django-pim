# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from django.db import models

logger = logging.getLogger(__name__)


class FilesCategory(models.Model):
    name_t9n = models.JSONField(null=False, default=dict)
    code = models.CharField(max_length=256, blank=False, null=False)
    db_created = models.DateTimeField(auto_now_add=True)
    objects = models.Manager()

    class Meta:
        ordering = ["-db_created"]
        verbose_name = "File category"
        verbose_name_plural = "File categories"

    def __str__(self):
        return f"{self.code}"

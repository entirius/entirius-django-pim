# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models


class AttributesGroup(models.Model):
    idx = models.CharField(max_length=128, blank=False, null=False, unique=True)
    name_t9n = models.JSONField(null=False, default=dict)
    desc = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Internal description / instruction. Used to ground AI workflows when matching "
            "(feature-set selection, attribute fill). Not shown on the storefront."
        ),
    )
    objects = models.Manager()

    def __str__(self):
        return self.idx

    class Meta:
        verbose_name = "Attributes Group"
        verbose_name_plural = "Attributes Groups"

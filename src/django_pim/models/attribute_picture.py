# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models


class AttributePicture(models.Model):
    attribute = models.ForeignKey("Attribute", related_name="pictures", on_delete=models.CASCADE)
    picture = models.ForeignKey(
        "Picture", related_name="attributes", verbose_name="picture", null=False, blank=False, on_delete=models.CASCADE
    )
    objects = models.Manager()

    def __str__(self):
        return f"[{self.attribute.idx}] {self.picture.id}"

    class Meta:
        ordering = []
        verbose_name_plural = "attributes pictures"
        constraints = [models.UniqueConstraint(fields=["attribute", "picture"], name="unique_attribute_picture")]

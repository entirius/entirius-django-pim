# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import hashlib
import logging
import os

from django.db import models
from django.dispatch import receiver

from ..utils.hashed_image_field_file import HashedImageField, UniqueFileSystemStorage

logger = logging.getLogger(__name__)


class Thumb(models.Model):
    image = HashedImageField(
        upload_to="thumb", storage=UniqueFileSystemStorage(), height_field="height", width_field="width", editable=False
    )
    sha1 = models.CharField(unique=True, max_length=40, default=None, blank=True, null=True)
    width = models.PositiveSmallIntegerField(blank=True, null=True)
    height = models.PositiveSmallIntegerField(blank=True, null=True)
    db_created = models.DateTimeField(auto_now_add=True)
    objects = models.Manager()

    def save(self, *args, **kwargs):
        if not self.pk:  # file is new
            if self.image.size <= 0:
                raise Exception("Can not save image with size=0")

            self.image.open()  # seek of closed file fix
            sha1 = hashlib.sha1()
            for chunk in self.image.chunks():
                sha1.update(chunk)
            self.sha1 = sha1.hexdigest()
        super().save(*args, **kwargs)

    @property
    def url(self):
        raise Exception(
            "TODO: przeniesc url do view, model moze dac path do pliku a url moze byc do niego wiele z wielu domen. Pliki maja juz extension"
        )
        # from django.conf import settings
        # sha = self.sha1
        # return "{}thumb/{}/{}/{}.png".format(
        #     settings.MEDIA_URL, sha[:2], sha[2:4], sha[4:]
        # )

    def __str__(self):
        return "%s - %sx%s" % (self.sha1, self.width, self.height)

    class Meta:
        ordering = ["-db_created"]
        verbose_name_plural = "thumbs"


# auto-delete files from filesystem when they are unneeded:
@receiver(models.signals.post_delete, sender=Thumb)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    """
    Deletes file from filesystem
    when corresponding `Thumb` object is deleted.
    """
    if instance.image:
        if os.path.isfile(instance.image.path):
            try:
                logger.info("Removing thumb file: %s" % instance.image.path)
                os.remove(instance.image.path)
            except Exception as e:
                logger.error("Can not remove thumb file: %s" % e)

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


class Picture(models.Model):
    image = HashedImageField(
        upload_to="image", storage=UniqueFileSystemStorage(), height_field="height", width_field="width", editable=False
    )
    sha1 = models.CharField(db_index=True, max_length=40, unique=True, default=None, blank=True, null=True)
    width = models.PositiveSmallIntegerField(blank=True, null=True)
    height = models.PositiveSmallIntegerField(blank=True, null=True)
    original_file_name = models.CharField(max_length=256, blank=True, null=True)
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

    def delete(self, *args, **kwargs):
        # Delete the picture's thumbnails first so their files are removed (Thumb has a post_delete
        # receiver that unlinks the file). The reverse accessor is `picture_thumbs` (the PictureThumb
        # join); each join points at one Thumb, and deleting the Thumb cascades the join away.
        # (`self.thumbs` never existed — this override used to raise AttributeError on every delete,
        # so thumb rows and files leaked.)
        for picture_thumb in self.picture_thumbs.all():
            picture_thumb.thumb.delete()
        super().delete(*args, **kwargs)

    def __str__(self):
        return "%s - %sx%s" % (self.sha1, self.width, self.height)

    class Meta:
        ordering = ["-db_created"]
        verbose_name_plural = "pictures"


# auto-delete files from filesystem when they are unneeded:
@receiver(models.signals.post_delete, sender=Picture)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    """
    Deletes file from filesystem
    when corresponding `Picture` object is deleted.
    """
    if instance.image:
        if os.path.isfile(instance.image.path):
            try:
                logger.info("Removing thumb file: %s" % instance.image.path)
                os.remove(instance.image.path)
            except Exception as e:
                logger.error("Can not remove picture file: %s" % e)

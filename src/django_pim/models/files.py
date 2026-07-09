# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from django.db import models

from ..utils.hashed_doc_field_file import HashedFileField, UniqueFileSystemStorage

logger = logging.getLogger(__name__)

from enum import IntEnum

from int_enum_choices import IntEnumChoices


class FileRoleEnum(IntEnum):
    UNDEFINED = 0
    PICTURE = 1
    PDF = 2
    DOC = 3
    VIDEO = 4


class FileRole(IntEnumChoices):
    enumClass = FileRoleEnum

    labels = {
        FileRoleEnum.UNDEFINED: "Undefined File Type",
        FileRoleEnum.PICTURE: "Picture File Type",
        FileRoleEnum.PDF: "PDF File Type",
        FileRoleEnum.DOC: "Document File Type",
        FileRoleEnum.VIDEO: "Video File Type",
    }


class Files(models.Model):
    file = HashedFileField(upload_to="files", storage=UniqueFileSystemStorage(), editable=False)
    file_category = models.ForeignKey(
        "FilesCategory",
        related_name="product_file_category",
        verbose_name="product_file_category",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    sha1 = models.CharField(db_index=True, max_length=40, unique=True, default=None, blank=True, null=True)
    original_file_name = models.CharField(max_length=256, blank=True, null=True)
    file_label = models.CharField(max_length=256, blank=True, null=True)
    file_label_t9n = models.JSONField(default=dict, blank=True)
    weight = models.CharField(max_length=20, blank=True, null=True)
    file_path = models.CharField(max_length=512, blank=True, null=True)
    file_type = models.PositiveSmallIntegerField(
        choices=FileRole.choices(), blank=False, null=False, default=FileRoleEnum.UNDEFINED
    )
    codec = models.CharField(max_length=20, blank=True, null=True)
    height = models.PositiveSmallIntegerField(blank=True, null=True)
    width = models.PositiveSmallIntegerField(blank=True, null=True)
    db_created = models.DateTimeField(auto_now_add=True)
    objects = models.Manager()

    def save(self, *args, **kwargs) -> None:
        super().save(*args, **kwargs)

    # NOTE: `Files` has no thumbnail relation — the previous `delete()` override iterated a
    # non-existent `self.thumbs` accessor and so raised AttributeError on every delete. Removed;
    # the default `Model.delete()` (which fires the cascade + post_delete signals) is correct here.

    def __str__(self):
        return "%s" % self.sha1

    class Meta:
        ordering = ["-db_created"]
        verbose_name = "File"
        verbose_name_plural = "Files"

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models
from django.utils.translation import gettext_lazy as _


class PictureThumb(models.Model):
    class TransformMethod(models.TextChoices):
        RESIZE_RATIO_SAFE_BG_WHITE = ("resize ratio, white", _("Resize ratio safe, white bg"))
        RESIZE_RATIO_SAFE_BG_BLACK = ("resize ratio, black", _("Resize ratio safe, black bg"))
        RESIZE_RATIO_SAFE_BG_PINK = ("resize ratio, pink", _("Resize ratio safe, pink bg"))
        RESIZE_RATIO_SAFE_BG_TRANSPARENT = ("resize ratio, transparent", _("Resize ratio safe, transparent bg"))
        RESIZE_FILL_CROP_BG_WHITE = "fill and crop, white", _("Fill and crop, white bg")
        RESIZE_FILL_CROP_BG_BLACK = "fill and crop, black", _("Fill and crop, black bg")
        RESIZE_FILL_CROP_BG_PINK = "fill and crop, pink", _("Fill and crop, pink bg")
        RESIZE_FILL_CROP_BG_TRANSPARENT = ("fill and crop, transparent", _("Fill and crop, transparent bg"))
        REMOVE_BACKGROUND_EXPERIMENTAL = ("remove background experimental", _("Remove background experimental"))
        REMOVE_BACKGROUND_EXPERIMENTAL_V2 = (
            "remove background experimental v2",
            _("Remove background experimental_v2"),
        )

    class ImageFormat(models.TextChoices):
        PNG = "png", "png"
        WEBP = "webp", "webp"
        JPG = "jpg", "jpg"
        GIF = "gif", "gif"

    picture = models.ForeignKey(
        "Picture",
        related_name="picture_thumbs",
        verbose_name="picture",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )
    thumb = models.ForeignKey(
        "Thumb", related_name="picture_thumbs", verbose_name="thumb", null=False, blank=False, on_delete=models.CASCADE
    )
    # width and height are args for transform function and can be null or differ from thumb size
    width = models.PositiveSmallIntegerField(blank=True, null=True)
    height = models.PositiveSmallIntegerField(blank=True, null=True)
    transform_method = models.CharField(
        max_length=34, choices=TransformMethod.choices, blank=False, null=False, db_index=True
    )
    out_format = models.CharField(max_length=4, choices=ImageFormat.choices, blank=False, null=False, db_index=True)
    db_created = models.DateTimeField(auto_now_add=True)
    objects = models.Manager()

    def __str__(self):
        return f"{self.picture.sha1}.{self.thumb.sha1} {self.width}x{self.height} {self.transform_method} {self.out_format}"

    class Meta:
        ordering = []
        verbose_name_plural = "picture thumbs"
        unique_together = ("picture", "thumb", "width", "height", "transform_method", "out_format")

    @property
    def get_transform_method(self):
        if self.transform_method is None:
            return None
        return self.TransformMethod(self.transform_method)

    @property
    def get_transform_method_name(self):
        if self.transform_method is None:
            return None
        return self.TransformMethod(self.transform_method).label

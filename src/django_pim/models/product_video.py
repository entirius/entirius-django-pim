# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from enum import IntEnum

from django.db import models
from int_enum_choices import IntEnumChoices


class VideoRoleEnum(IntEnum):
    UNKNOWN = 0
    MAIN = 1
    VARIANT = 2


class VideoRole(IntEnumChoices):
    enumClass = VideoRoleEnum

    labels = {
        VideoRoleEnum.UNKNOWN: "Unknown Video",
        VideoRoleEnum.MAIN: "Main Product Video",
        VideoRoleEnum.VARIANT: "Variant Video",
    }


class VideoRoleApiLabel(IntEnumChoices):
    enumClass = VideoRoleEnum

    labels = {VideoRoleEnum.UNKNOWN: "unknown", VideoRoleEnum.MAIN: "main", VideoRoleEnum.VARIANT: "variant"}


class ProductVideo(models.Model):
    product = models.ForeignKey(
        "Product", related_name="videos", verbose_name="product", null=False, blank=False, on_delete=models.CASCADE
    )

    video = models.ForeignKey(
        "Video", related_name="products", verbose_name="video", null=False, blank=False, on_delete=models.CASCADE
    )

    video_role = models.PositiveSmallIntegerField(
        choices=VideoRole.choices(), blank=False, null=False, default=VideoRoleEnum.UNKNOWN
    )
    # if language is null, then video is available in all languages
    # (I think it's better than many to many and all languages by default)
    language = models.ForeignKey(
        "django_regional.Language",
        related_name="product_videos",
        verbose_name="language",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        default=None,
    )

    position = models.IntegerField(default=0, blank=True, null=False)
    is_inherited = models.BooleanField(default=False)
    objects = models.Manager()

    def __str__(self):
        return f"{self.product.id} {self.video.id} {self.video_role}"

    def get_role_api_label(self):
        return VideoRoleApiLabel.labelFromId(self.video_role)

    class Meta:
        ordering = []
        verbose_name_plural = "products videos"
        constraints = [
            # produkt moze posiadac tylko jedno zdjecie w roli "MAIN"
            # dla danego jezyka lub dla wszystkich jezykow (language=None)
            models.UniqueConstraint(
                fields=["product", "video_role", "language"],
                condition=models.Q(video_role=VideoRoleEnum.MAIN),
                name="unique_product_video_main",
            ),
            # produkt moze posiadac dowolna ilosc zdjec typu "VARIANT",
            # ale dane zdjecie nie moze sie powtorzyc w tej roli
            models.UniqueConstraint(
                fields=["product", "video", "language"],
                condition=models.Q(video_role=VideoRoleEnum.VARIANT),
                name="unique_product_video_variant",
            ),
        ]

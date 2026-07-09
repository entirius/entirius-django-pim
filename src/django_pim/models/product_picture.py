# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from enum import IntEnum

from django.db import models
from int_enum_choices import IntEnumChoices


class PictureRoleEnum(IntEnum):
    UNKNOWN = 0
    MAIN = 1
    GENERAL = 2  # zdjecie ogolne produktu
    VARIANT = 3  # w Kamino uzywane jako variant
    ANGLE = 4  # zdjecia pod innymi katami


class PictureRole(IntEnumChoices):
    enumClass = PictureRoleEnum

    labels = {
        PictureRoleEnum.MAIN: "Main Product Picture",
        PictureRoleEnum.GENERAL: "General Product Picture",
        PictureRoleEnum.UNKNOWN: "Unknown Role Picture",
        PictureRoleEnum.VARIANT: "Variant Picture",
        PictureRoleEnum.ANGLE: "Another Angle Picture",
    }


class PictureRoleApiLabel(IntEnumChoices):
    enumClass = PictureRoleEnum

    labels = {
        PictureRoleEnum.MAIN: "main",
        PictureRoleEnum.GENERAL: "general",
        PictureRoleEnum.UNKNOWN: "unknown",
        PictureRoleEnum.VARIANT: "variant",
        PictureRoleEnum.ANGLE: "angle",
    }


class ProductPicture(models.Model):
    product = models.ForeignKey(
        "Product", related_name="pictures", verbose_name="product", null=False, blank=False, on_delete=models.CASCADE
    )

    picture = models.ForeignKey(
        "Picture", related_name="products", verbose_name="picture", null=False, blank=False, on_delete=models.CASCADE
    )

    picture_role = models.PositiveSmallIntegerField(
        choices=PictureRole.choices(), blank=False, null=False, default=PictureRoleEnum.UNKNOWN
    )
    # if language is null, then picture is available in all languages (I think it's better than many to many and all languages by default)
    language = models.ForeignKey(
        "django_regional.Language",
        related_name="product_pictures",
        verbose_name="language",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        default=None,
    )

    position = models.IntegerField(default=0, blank=True, null=False)
    alt_text_t9n = models.JSONField(default=dict, blank=True)
    is_inherited = models.BooleanField(default=False)
    objects = models.Manager()

    def get_role_api_label(self):
        return PictureRoleApiLabel.labelFromId(self.picture_role)

    def __str__(self):
        return "%s %s %s" % (self.product.id, self.picture.id, self.picture_role)

    class Meta:
        ordering = []
        verbose_name_plural = "products pictures"
        constraints = [
            # produkt moze posiadac tylko jedno zdjecie w roli "MAIN" dla danego jezyka lub dla wszystkich jezykow (language=None)
            models.UniqueConstraint(
                fields=["product", "picture_role", "language"],
                condition=models.Q(picture_role=PictureRoleEnum.MAIN),
                name="unique_product_picture_main",
            ),
            # produkt moze posiadac dowolna ilosc zdjec typu "GENERAL",
            # ale dane zdjecie nie moze sie powtorzyc w tej roli
            models.UniqueConstraint(
                fields=["product", "picture", "language"],
                condition=models.Q(picture_role=PictureRoleEnum.GENERAL),
                name="unique_product_picture_general",
            ),
            # produkt moze posiadac dowolna ilosc zdjec typu "ANGLE",
            # ale dane zdjecie nie moze sie powtorzyc w tej roli
            models.UniqueConstraint(
                fields=["product", "picture", "language"],
                condition=models.Q(picture_role=PictureRoleEnum.ANGLE),
                name="unique_product_picture_angle",
            ),
            # produkt moze posiadac dowolna ilosc zdjec typu "VARIANT",
            # ale dane zdjecie nie moze sie powtorzyc w tej roli
            models.UniqueConstraint(
                fields=["product", "picture", "language"],
                condition=models.Q(picture_role=PictureRoleEnum.VARIANT),
                name="unique_product_picture_variant",
            ),
        ]

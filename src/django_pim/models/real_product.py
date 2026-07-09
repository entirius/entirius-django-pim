# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from enum import IntEnum

from django.db import models
from django.db.models import UniqueConstraint
from django.db.models.functions import Lower
from django_utils.managers.enhance_manager import EnhanceManager
from idx_normalizator import normalize_sku, validate_ean, validate_sku
from int_enum_choices import IntEnumChoices

from django_pim.validators import validate_routable_sku


class KindOfProductEnum(IntEnum):
    ProductPhysical = 0
    ProductVirtual = 1


class KindOfProductClass(IntEnumChoices):
    enumClass = KindOfProductEnum

    labels = {
        KindOfProductEnum.ProductPhysical: "Product Physical",
        KindOfProductEnum.ProductVirtual: "Product Virtual",
    }


class RealProduct(models.Model):
    sku = models.CharField(max_length=128, blank=False, null=False)
    ean = models.CharField(db_index=True, max_length=16, blank=True, null=True)
    kind_of_product = models.PositiveSmallIntegerField(
        choices=KindOfProductClass.choices(), blank=False, null=False, default=KindOfProductEnum.ProductPhysical
    )
    # weight unit is defined in settings.PIM_weight_UNIT
    weight = models.DecimalField(blank=True, null=True, max_digits=12, decimal_places=2)
    # dimensions unit is defined in settings.PIM_DIMENSIONS_UNIT
    width = models.DecimalField(blank=True, null=True, max_digits=12, decimal_places=2)
    height = models.DecimalField(blank=True, null=True, max_digits=12, decimal_places=2)
    deep = models.DecimalField(blank=True, null=True, max_digits=12, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)
    objects = EnhanceManager()

    def save(self, ignore_validate_ean: bool = False, *args, **kwargs):
        validate_sku(self.sku)
        validate_routable_sku(self.sku)
        if not ignore_validate_ean:
            validate_ean(self.ean)
        super().save(*args, **kwargs)

    @staticmethod
    def normalize_sku(sku):
        """Deprecated"""
        return normalize_sku(sku)

    @staticmethod
    def validate_sku(sku):
        """Deprecated"""
        return validate_sku(sku)

    @property
    def kind_of_product_name(self):
        return KindOfProductClass.labelFromId(self.kind_of_product)

    def __str__(self):
        return self.sku

    class Meta:
        ordering = ["id"]
        verbose_name_plural = "real products"
        constraints = [UniqueConstraint(Lower("sku"), name="unique_real_product_sku")]
        indexes = [models.Index(Lower("sku"), "id", name="idx_realproduct_sku_lower")]

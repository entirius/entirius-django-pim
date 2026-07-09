# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from enum import IntEnum

from django.conf import settings
from django.db import models
from int_enum_choices import IntEnumChoices


class SectionTypeEnum(IntEnum):
    INCLUDED_PRODUCTS = 0


#    # ONE_TO_MANY = 1


class SectionType(IntEnumChoices):
    enumClass = SectionTypeEnum
    labels = {SectionTypeEnum.INCLUDED_PRODUCTS: "Included Products"}


class BundleLink(models.Model):
    product_bundle = models.ForeignKey(
        "ProductBundle",
        related_name="bundle_links",
        verbose_name="product_bundle",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )

    subproduct = models.ForeignKey(
        "Product",
        related_name="bundle_sub_links",
        verbose_name="subproduct_bundle",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )
    quantity = models.PositiveIntegerField(blank=False, null=False, default=1)
    section = models.ForeignKey(
        "BundleSection",
        related_name="bundle_section",
        verbose_name="Bundle Sections",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )
    order = models.PositiveIntegerField(blank=False, null=False, default=1)
    can_change_quantity = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    is_required = models.BooleanField(default=False)
    objects = models.Manager()

    def __str__(self):
        return f"{self.product_bundle}"

    class Meta:
        ordering = []
        verbose_name_plural = "bundle links"
        unique_together = (("product_bundle", "subproduct"),)


class BundleSection(models.Model):
    idx = models.CharField(max_length=64, blank=False, null=False, unique=True)
    name = models.JSONField(null=True, blank=True, default=dict)
    desc = models.JSONField(null=True, blank=True, default=dict)
    section_type = models.PositiveSmallIntegerField(
        choices=SectionType.choices(), blank=False, null=False, default=SectionTypeEnum.INCLUDED_PRODUCTS
    )
    objects = models.Manager()

    def __str__(self):
        return f"{self.idx}"

    def name_lang(self, lang):
        langs = [lang, settings.T9N_DEFAULT_LANG] if lang != settings.T9N_DEFAULT_LANG else [lang]
        for lang in langs:
            if lang in self.name:
                name = self.name[lang]
                if name:
                    return str(name).strip() if len(name.strip()) > 0 else None
        return self.idx

    def desc_lang(self, lang):
        langs = [lang, settings.T9N_DEFAULT_LANG] if lang != settings.T9N_DEFAULT_LANG else [lang]
        for lang in langs:
            if lang in self.desc:
                desc = self.desc[lang]
                if desc:
                    return str(desc).strip() if len(desc.strip()) > 0 else None
        return self.idx

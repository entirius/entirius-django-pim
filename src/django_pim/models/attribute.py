# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import hashlib
from enum import IntEnum

from django.conf import settings
from django.db import models
from django.db.models import Count, F, Prefetch, Q
from idx_normalizator import validate_idx
from int_enum_choices import IntEnumChoices
from slugify import slugify

from django_pim.models.feature import Feature


class Attribute(models.Model):
    feature = models.ForeignKey(
        "Feature", related_name="attributes", verbose_name="feature", null=False, blank=False, on_delete=models.CASCADE
    )
    idx = models.CharField(max_length=128, blank=False, null=False)
    extension = models.JSONField(null=True, blank=True)
    magento_idx = models.CharField(max_length=26, blank=True, null=True)
    magento_pk = models.IntegerField(blank=True, null=True)
    name_t9n = models.JSONField(null=False, default=dict)
    desc = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Internal description / instruction. Used to ground AI workflows when matching "
            "(feature-set selection, attribute fill). Not shown on the storefront."
        ),
    )
    display_order = models.PositiveSmallIntegerField(blank=False, null=False, default=100)
    group = models.ForeignKey(
        "AttributesGroup",
        related_name="attributes",
        verbose_name="attributes group",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    objects = models.Manager()

    @property
    def name(self):
        return self.name_lang(lang=settings.T9N_DEFAULT_LANG)

    def name_lang(self, lang):
        langs = [lang]
        if lang != settings.T9N_DEFAULT_LANG:
            langs.append(settings.T9N_DEFAULT_LANG)
        for lang in langs:
            if lang in self.name_t9n:
                name = self.name_t9n[lang]
                if name is not None:
                    name = str(name)
                    name = name.strip()
                    if len(name) > 0:
                        return name
        return self.idx

    @staticmethod
    def generate_magento_idx(idx):
        MAX = 26  # magento przyjmuje max 30 minus 4 na prefix
        HASHLEN = 8  # dlugosc hasha
        separator = "_"
        idx = slugify(idx, separator=separator)
        if len(idx) > MAX:
            prefix = idx[: MAX - HASHLEN - 1]
            rest = idx[MAX - HASHLEN - 1 :]
            rest = rest.encode("utf-8")
            m = hashlib.md5()
            m.update(rest)
            h = m.hexdigest()
            idx = "%s%s%s" % (prefix, separator, h[:HASHLEN])
        return idx

    def save(self, *args, **kwargs):
        self.name_t9n = dict(self.name_t9n)
        validate_idx(str(self.idx), min_len=1, max_len=128)
        if self.magento_idx is None:
            self.magento_idx = Attribute.generate_magento_idx(self.idx)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.feature.idx}]:[{self.idx}] {self.name}"

    class Meta:
        ordering = ["feature__idx", "idx"]
        verbose_name_plural = "attributes"
        unique_together = (("feature", "idx"), ("feature", "magento_idx"))
        indexes = [models.Index(fields=["feature"], name="idx_attr_feature_optimized", include=["id", "idx"])]


class AttributeModifierQuerySet(models.QuerySet):
    def filter_by_all_attributes(self, attributes):
        q = Q()
        for attribute in attributes:
            q &= Q(attributes=attribute)
        return self.annotate(c=Count("attributes")).filter(c=len(attributes)).filter(q)

    def filter_by_all_groups(self, groups):
        q = Q()
        for group in groups:
            q &= Q(groups=group)
        return self.annotate(c=Count("groups")).filter(c=len(groups)).filter(q)

    def filter_by_all_possible_groups(self, possible_groups):
        return self.annotate(
            num_related_g_total=Count("groups", distinct=True),
            num_related_g_in_list=Count("groups", filter=Q(groups__idx__in=possible_groups), distinct=True),
        ).filter(num_related_g_total=F("num_related_g_in_list"))

    def filter_by_all_possible_attributes(self, possible_attributes):
        return self.annotate(
            num_related_total=Count("attributes", distinct=True),
            num_related_in_list=Count("attributes", filter=Q(attributes__idx__in=possible_attributes), distinct=True),
        ).filter(num_related_total=F("num_related_in_list"))


class AttributeModifierManager(models.Manager):
    def get_queryset(self):
        return AttributeModifierQuerySet(self.model, using=self.db)

    def _get_intersection_of_two_features(self, feature1, feature2, chosen_attributes=None):

        feature1 = Feature.objects.get(idx=feature1)
        feature2 = Feature.objects.get(idx=feature2)
        chosen_group_1 = None
        chosen_group_2 = None
        for f9e, data in chosen_attributes.items():
            if f9e == feature1.idx:
                chosen_group_1 = data[0].get("group__idx", None)
            elif f9e == feature2.idx:
                chosen_group_2 = data[0].get("group__idx", None)

        attr_1_chosen = [Q(group__idx=chosen_group_1) | Q(group=None)] if chosen_group_1 else []
        attr_2_chosen = [Q(group__idx=chosen_group_2) | Q(group=None)] if chosen_group_2 else []

        intersection_exists = self.filter(
            (Q(feature=feature1) & Q(feature_modified=feature2)) | (Q(feature_modified=feature2) & Q(feature=feature1)),
            modifier_type=AttributeModifierTypeEnum.COLOR_HASH_INTERSECTION,
        ).exists()

        if not intersection_exists:
            raise ValueError("Intersection not found")

        from django_pim.models.product_attribute_image import ProductAttributeImage

        attrs_1 = Attribute.objects.filter(Q(feature=feature1), *attr_1_chosen).prefetch_related(
            Prefetch("attribute_picture", queryset=ProductAttributeImage.objects.select_related("product"))
        )
        attrs_2 = Attribute.objects.filter(Q(feature=feature2), *attr_2_chosen).prefetch_related(
            Prefetch("attribute_picture", queryset=ProductAttributeImage.objects.select_related("product"))
        )

        attrs_1_idxs = []
        attrs_2_idxs = []
        attrs_colors_match = {}
        for attr_1 in attrs_1:
            color_hash_1 = next(
                (
                    pic.color_hash
                    for pic in attr_1.attribute_picture.all()
                    if pic.product is None and pic.color_hash is not None
                ),
                None,
            )
            for attr_2 in attrs_2:
                color_hash_2 = next(
                    (
                        pic.color_hash
                        for pic in attr_2.attribute_picture.all()
                        if pic.product is None and pic.color_hash is not None
                    ),
                    None,
                )
                if color_hash_1 is None or color_hash_2 is None:
                    continue
                if color_hash_1 == color_hash_2:
                    attrs_1_idxs.append(attr_1.idx)
                    attrs_2_idxs.append(attr_2.idx)
                    attrs_colors_match[attr_1] = attr_2
                    attrs_colors_match[attr_2] = attr_1
        return (feature1, attrs_1_idxs), (feature2, attrs_2_idxs), attrs_colors_match

    def get_all_intersection_of_two_features(self, chosen_attributes=None):
        all_intersection_modifiers = self.filter(
            modifier_type=AttributeModifierTypeEnum.COLOR_HASH_INTERSECTION
        ).select_related("feature", "feature_modified")
        for intersection_modifier in all_intersection_modifiers:
            feature1 = intersection_modifier.feature.idx
            feature2 = intersection_modifier.feature_modified.idx
            yield self._get_intersection_of_two_features(feature1, feature2, chosen_attributes)

    def create_or_update(
        self,
        product,
        real_product,
        feature,
        groups,
        feature_modified,
        attribute_modified,
        attribute_coerced,
        modifier_type,
        attributes,
        idx,
        value_modifier,
        csv_row_hash,
    ):
        is_created = False

        attr = (
            self.filter(
                product=product,
                real_product=real_product,
                feature=feature,
                feature_modified=feature_modified,
                attribute_modified=attribute_modified,
                attribute_coerced=attribute_coerced,
                modifier_type=modifier_type,
            )
            .filter_by_all_attributes(attributes)
            .filter_by_all_groups(groups)
            .first()
        )
        if not attr:
            is_created = True
            attr = AttributeModifier(
                product=product,
                real_product=real_product,
                feature=feature,
                feature_modified=feature_modified,
                attribute_modified=attribute_modified,
                attribute_coerced=attribute_coerced,
                modifier_type=modifier_type,
                value_modifier=value_modifier,
                source_id=idx,
                csv_row_hash=csv_row_hash,
            )
            attr.save()
            attr.attributes.set(attributes)
            attr.groups.set(groups)

        attr.value_modifier = value_modifier
        attr.source_id = idx
        attr.csv_row_hash = csv_row_hash
        attr.save()
        return attr, is_created


class AttributeModifierTypeEnum(IntEnum):
    UNKNOWN = 1
    VALUE = 2
    EXCLUDE = 3
    COLOR_HASH_INTERSECTION = 4
    DEFAULT = 5
    COERCE = 6


class AttributeModifierType(IntEnumChoices):
    enumClass = AttributeModifierTypeEnum
    labels = {
        AttributeModifierTypeEnum.UNKNOWN: "unknown",
        AttributeModifierTypeEnum.VALUE: "value",
        AttributeModifierTypeEnum.EXCLUDE: "exclude",
        AttributeModifierTypeEnum.COLOR_HASH_INTERSECTION: "color_hash_intersection",
        AttributeModifierTypeEnum.DEFAULT: "default",
        AttributeModifierTypeEnum.COERCE: "coerce",
    }

    @staticmethod
    def get_modifier_type_int(label: str) -> int:
        for key, value in AttributeModifierType.labels.items():
            if value == label:
                return key
        raise ValueError(f"Label '{label}' not found in AttributeModifierType labels.")


class AttributeModifier(models.Model):
    source_id = models.FloatField()
    product = models.ForeignKey(
        "Product",
        related_name="product_modifier_custom",
        verbose_name="product",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    real_product = models.ForeignKey(
        "RealProduct",
        related_name="real_product_modifier_custom",
        verbose_name="real product",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    feature = models.ForeignKey(
        "Feature",
        related_name="feature_modifier_custom",
        verbose_name="Added feature to custom",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    attributes = models.ManyToManyField(
        "Attribute", related_name="attributes_modifier_custom", verbose_name="Added attributes to custom", blank=True
    )
    groups = models.ManyToManyField(
        "AttributesGroup", related_name="groups_modifier_custom", verbose_name="Added group to custom", blank=True
    )
    feature_modified = models.ForeignKey(
        "Feature",
        related_name="feature_modified",
        verbose_name="Modified/Excluded Feature",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    attribute_modified = models.ForeignKey(
        "Attribute",
        related_name="attributes_modified",
        verbose_name="Modified/Excluded Attribute",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    attribute_coerced = models.ForeignKey(
        "Attribute",
        related_name="attributes_coerced",
        verbose_name="Coerced Attribute",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    modifier_type = models.PositiveSmallIntegerField(
        choices=AttributeModifierType.choices(), blank=False, null=False, default=AttributeModifierTypeEnum.UNKNOWN
    )
    value_modifier = models.DecimalField(max_digits=64, decimal_places=12, blank=True, null=True, default=0)
    csv_row_hash = models.CharField(max_length=3000, blank=True, null=True)
    objects = AttributeModifierManager()

    class Meta:
        ordering = ["feature_modified"]
        verbose_name_plural = "attribute modifiers"

    def __str__(self):
        return f"{self.pk}"

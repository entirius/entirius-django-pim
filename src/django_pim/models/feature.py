# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import hashlib
from enum import IntEnum

from django.db import models
from idx_normalizator import validate_idx
from int_enum_choices import IntEnumChoices
from slugify import slugify

from django_pim.workers.unit_conversion import Length, Mass, Temperature

from .. import settings


class FeatureTypeEnum(IntEnum):
    UNKNOWN = 0
    BOOL = 1
    DECIMAL = 2
    VARCHAR255 = 3
    VARCHAR255_T9N = 4
    TEXT = 5
    TEXT_T9N = 6
    SELECT = 7
    MULTISELECT = 8
    JSON = 9
    DATETIME = 10
    JSON_T9N = 11
    TEMPERATURE = 12
    LENGTH = 13
    MASS = 14


class FeatureType(IntEnumChoices):
    enumClass = FeatureTypeEnum
    labels = {
        FeatureTypeEnum.UNKNOWN: "Unknown",
        FeatureTypeEnum.BOOL: "Bool",
        FeatureTypeEnum.DECIMAL: "Decimal",
        FeatureTypeEnum.VARCHAR255: "Varchar 255",
        FeatureTypeEnum.VARCHAR255_T9N: "Varchar 255 t9n",
        FeatureTypeEnum.TEXT: "Text",
        FeatureTypeEnum.TEXT_T9N: "Text t9n",
        FeatureTypeEnum.SELECT: "Select",
        FeatureTypeEnum.MULTISELECT: "Multiselect",
        FeatureTypeEnum.JSON: "Json",
        FeatureTypeEnum.JSON_T9N: "Json t9n",
        FeatureTypeEnum.DATETIME: "Datetime",
        FeatureTypeEnum.TEMPERATURE: "Temperature",
        FeatureTypeEnum.LENGTH: "Length",
        FeatureTypeEnum.MASS: "Mass",
    }


class FeatureScopeEnum(IntEnum):
    SYSTEM = 1
    GLOBAL = 2
    BUSINESS_UNIT = 3


class FeatureScope(IntEnumChoices):
    enumClass = FeatureScopeEnum
    labels = {
        FeatureScopeEnum.SYSTEM: "system",
        FeatureScopeEnum.GLOBAL: "global",
        FeatureScopeEnum.BUSINESS_UNIT: "business unit",
    }


class FrontendInputTypeEnum(IntEnum):
    DEFAULT = 0
    SELECT_SWATCH_VISUAL = 1
    SELECT_SWATCH_TEXT = 2
    DROPDOWN = 3
    DROPDOWN_WITH_PRICE = 4
    PALETTE_COLOR = 5
    SLIDER = 6
    BOOLEAN = 7
    RADIO = 8


class FrontendInputType(IntEnumChoices):
    enumClass = FrontendInputTypeEnum
    labels = {
        FrontendInputTypeEnum.DEFAULT: "Default",
        FrontendInputTypeEnum.SELECT_SWATCH_VISUAL: "Swatch_Visual",
        FrontendInputTypeEnum.SELECT_SWATCH_TEXT: "Swatch_Text",
        FrontendInputTypeEnum.DROPDOWN: "dropdown",
        FrontendInputTypeEnum.DROPDOWN_WITH_PRICE: "dropdown_with_price",
        FrontendInputTypeEnum.PALETTE_COLOR: "palette_color",
        FrontendInputTypeEnum.SLIDER: "slider",
        FrontendInputTypeEnum.BOOLEAN: "boolean",
        FrontendInputTypeEnum.RADIO: "radio",
    }


class FilterTypeEnum(IntEnum):
    DEFAULT = 0
    SELECT_SWATCH_IMAGE = 1
    SELECT_SWATCH_TEXT = 2
    SLIDE = 3
    BOOLEAN = 4
    RADIO_TEXT = 5


class FilterType(IntEnumChoices):
    enumClass = FilterTypeEnum
    labels = {
        FilterTypeEnum.DEFAULT: "Default",
        FilterTypeEnum.SELECT_SWATCH_IMAGE: "Swatch_Image",
        FilterTypeEnum.SELECT_SWATCH_TEXT: "Swatch_Text",
        FilterTypeEnum.SLIDE: "Slide",
        FilterTypeEnum.BOOLEAN: "Boolean",
        FilterTypeEnum.RADIO_TEXT: "Radio_Text",
    }


class FeatureManager(models.Manager):
    def get_or_none(self, **kwargs):
        try:
            return self.get(**kwargs)
        except self.model.DoesNotExist:
            return None

    def get_scoped_feature(self, feature_idx):
        return self.model.objects.get(idx=feature_idx)

    def get_system_features(self):
        return self.filter(scope=FeatureScopeEnum.SYSTEM).order_by("display_order")

    def get_shop_features(self, shop, system_features=False):
        if system_features:
            features = list(self.get_system_features())
        else:
            features = []
        features += list(self.filter(scope=FeatureScopeEnum.BUSINESS_UNIT).order_by("display_order"))
        return features

    def availability_table(self, print_out=True):
        all_objects = self.all()
        tpl = "| {:<6} | {:<42} | {:<87} |"
        tpl_all = "| {:<123} |"
        tpl_row = tpl.replace("|", "+")
        tpl_row = tpl_row.replace(":", ":-")
        tpl_row = tpl_row.replace(" ", "-")
        tpl_row = tpl_row.format("", "", "", "", "", "")

        txts = ["Available Features:"]
        txts.append(tpl_row)
        txts.append(tpl.format("id", "idx", "name"))
        txts.append(tpl_row)
        for obj in all_objects:
            txts.append(tpl.format(obj.id, obj.idx, obj.name))
        if len(all_objects) == 0:
            txts.append(tpl_all.format("no Features are available"))
        txts.append(tpl_row)
        txt = "\n".join(txts)
        if print_out:
            print("\n" + txt, flush=True)
        return txt


class Feature(models.Model):
    scope = models.PositiveSmallIntegerField(
        choices=FeatureScope.choices(), blank=False, null=False, default=FeatureScopeEnum.BUSINESS_UNIT
    )
    idx = models.CharField(unique=True, max_length=128, blank=False, null=False)
    features_sets = models.ManyToManyField(
        "FeatureSet", related_name="features", verbose_name="features_sets", blank=True, through="FeatureInFeatureSet"
    )
    magento_idx = models.CharField(unique=True, max_length=26, blank=True, null=True)
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
    is_required = models.BooleanField(default=False)
    is_visible = models.BooleanField(default=True)
    is_filterable = models.BooleanField(default=False)
    is_searchable = models.BooleanField(default=True)
    is_comparable = models.BooleanField(default=False)
    is_for_customization = models.BooleanField(default=False)
    exclude_from_inheritance = models.BooleanField(
        default=False, help_text="When True, this feature is never inherited — always independent per channel."
    )
    has_visual_asset = models.BooleanField(
        default=False,
        help_text="When True, this feature's attribute values carry associated visual assets (icon, swatch, badge).",
    )
    is_seo = models.BooleanField(
        default=False,
        help_text="When True, this feature is an SEO metadata field (meta_title, meta_description, etc.).",
    )
    extra_value = models.JSONField(null=True, blank=True, default=dict)
    feature_type = models.PositiveSmallIntegerField(
        choices=FeatureType.choices(), blank=False, null=False, default=FeatureTypeEnum.UNKNOWN
    )
    frontend_input_type = models.PositiveSmallIntegerField(
        choices=FrontendInputType.choices(), blank=False, null=False, default=FrontendInputTypeEnum.DEFAULT
    )
    filter_type = models.PositiveSmallIntegerField(
        choices=FilterType.choices(), blank=False, null=False, default=FilterTypeEnum.DEFAULT
    )
    display_order = models.PositiveSmallIntegerField(blank=False, null=False)
    objects = FeatureManager()

    @property
    def scope_name(self):
        return FeatureScope.labelFromId(self.scope)

    def get_cls_unit_conversion(self):
        if self.feature_type not in [FeatureTypeEnum.LENGTH, FeatureTypeEnum.MASS, FeatureTypeEnum.TEMPERATURE]:
            return None, None

        match self.feature_type:
            case FeatureTypeEnum.LENGTH:
                default_unit = settings.DEFAULT_LENGTH_UNIT
                model_unit = Length
            case FeatureTypeEnum.MASS:
                default_unit = settings.DEFAULT_MASS_UNIT
                model_unit = Mass
            case FeatureTypeEnum.TEMPERATURE:
                default_unit = settings.DEFAULT_TEMPERATURE_UNIT
                model_unit = Temperature
            case _:
                raise Exception(f"Unavailable feature type for unit conversion: {self.feature_type}")
        return default_unit, model_unit

    @property
    def frontend_input_type_name(self):
        return FrontendInputType.labelFromId(self.frontend_input_type)

    def get_extra_value_lang(self, language: str):
        return (
            {k: v.get(language, v) if isinstance(v, dict) else v for k, v in self.extra_value.items()}
            if isinstance(self.extra_value, dict)
            else {}
        )

    @property
    def feature_type_name(self):
        return FeatureType.labelFromId(self.feature_type)

    @property
    def filter_type_name(self):
        return FilterType.labelFromId(self.filter_type)

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

    def validate_system_features(self):
        if self.scope != FeatureScopeEnum.SYSTEM:
            assert self.idx not in settings.SYSTEM_FEATURES_IDXS, (
                f"Feature idx={self.idx} is reserved for system features"
            )

    # checking if it is compatible with feature_type
    def validate_frontend_input_type(self):
        if self.frontend_input_type in [
            FrontendInputTypeEnum.SELECT_SWATCH_VISUAL,
            FrontendInputTypeEnum.SELECT_SWATCH_TEXT,
        ]:
            if self.feature_type not in [FeatureTypeEnum.SELECT, FeatureTypeEnum.MULTISELECT]:
                raise Exception("Select Swatches can be used only with FeatureTypeEnum.SELECT or MULTISELECT")

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

    def check_display_order(self):
        if self.display_order is None:
            priorities = {FeatureScopeEnum.SYSTEM: 10, FeatureScopeEnum.GLOBAL: 90, FeatureScopeEnum.BUSINESS_UNIT: 110}
            self.display_order = priorities[self.scope]

    def save(self, *args, **kwargs):
        self.name_t9n = dict(self.name_t9n)
        validate_idx(str(self.idx), min_len=1, max_len=128)
        self.validate_frontend_input_type()
        if self.magento_idx is None:
            self.magento_idx = Feature.generate_magento_idx(self.idx)
        self.validate_system_features()
        self.check_display_order()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.idx}"

    class Meta:
        ordering = ["idx"]
        verbose_name_plural = "features"

        indexes = [models.Index(fields=["feature_type"], name="idx_feature_type_optimized", include=["id", "idx"])]

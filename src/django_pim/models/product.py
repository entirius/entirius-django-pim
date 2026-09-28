# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import hashlib
import logging
from decimal import Decimal
from enum import IntEnum

from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import Q
from django_utils.managers.enhance_manager import EnhanceManager
from int_enum_choices import IntEnumChoices
from slugify import slugify

from ..settings import (
    IS_DEFAULT_LANG_FOR_CHANNELS_FROM_PIM,
    SYSTEM_FEATURE_DESCRIPTION_IDX,
    SYSTEM_FEATURE_NAME_IDX,
    SYSTEM_FEATURE_SHORT_DESCRIPTION_IDX,
    SYSTEM_FEATURE_URL_KEY_IDX,
    SYSTEM_FEATURE_VOLUME_IDX,
    T9N_DEFAULT_LANG,
)
from .feature import FeatureScopeEnum, FeatureTypeEnum
from .gap_definition import GapSeverity
from .product_picture import PictureRoleEnum


class ProductClassEnum(IntEnum):
    ProductBase = 0
    ProductSimple = 1
    ProductConfigurable = 2
    ProductBundle = 3
    ProductCustom = 4


class ProductClass(IntEnumChoices):
    enumClass = ProductClassEnum

    labels = {
        # child job class names
        ProductClassEnum.ProductBase: "ProductBase",
        ProductClassEnum.ProductSimple: "ProductSimple",
        ProductClassEnum.ProductConfigurable: "ProductConfigurable",
        ProductClassEnum.ProductBundle: "ProductBundle",
        ProductClassEnum.ProductCustom: "ProductCustom",
    }


class ProductVisibilityEnum(IntEnum):
    UNKNOWN = 0
    NOT_VISIBLE_INDIVIDUALLY = 1
    CATALOG = 2
    SEARCH = 3
    CATALOG_AND_SEARCH = 4


class ProductVisibility(IntEnumChoices):
    enumClass = ProductVisibilityEnum

    labels = {
        ProductVisibilityEnum.NOT_VISIBLE_INDIVIDUALLY: "Not visible individually",
        ProductVisibilityEnum.CATALOG: "Catalog",
        ProductVisibilityEnum.SEARCH: "Search",
        ProductVisibilityEnum.CATALOG_AND_SEARCH: "Catalog and search",
        ProductVisibilityEnum.UNKNOWN: "Unknown",
    }


logger = logging.getLogger(__name__)


class ProductQuerySet(models.QuerySet):
    def catalog_visible(self):
        visibilities = ["Catalog and search", "Catalog"]
        visibility_ids = [ProductVisibility.idFromText(visibility) for visibility in visibilities]

        return self.filter(is_enabled=True, categories__is_active=True, visibility__in=visibility_ids).distinct()

    def catalog_filterable(self):
        visibilities = ["Catalog and search", "Catalog"]
        visibility_ids = [ProductVisibility.idFromText(visibility) for visibility in visibilities]
        is_visible = Q(is_enabled=True, categories__is_active=True, visibility__in=visibility_ids)
        parent_is_visible = Q(configurable_links__product_configurable__product_ptr__in=self.filter(is_visible))
        query = is_visible | parent_is_visible
        return self.filter(query).distinct()


class ProductManager(EnhanceManager):
    def get_queryset(self):
        return ProductQuerySet(self.model, using=self.db)

    def catalog_visible(self):
        return self.get_queryset().catalog_visible()

    def catalog_filterable(self):
        return self.get_queryset().catalog_filterable()


class Product(models.Model):
    product_class = models.SmallIntegerField(
        choices=ProductClass.choices(), db_index=True, blank=False, null=False, default=ProductClassEnum.ProductBase
    )
    real_product = models.ForeignKey(
        "RealProduct",
        related_name="products",
        verbose_name="real_product",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )
    shop = models.ForeignKey(
        "Channel", related_name="products", verbose_name="shop", null=False, blank=False, on_delete=models.CASCADE
    )
    feature_set = models.ForeignKey(
        "FeatureSet",
        related_name="products",
        verbose_name="feature_set",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )
    categories = models.ManyToManyField(
        "ProductCategory", related_name="products", verbose_name="categories", blank=True, through="ProductInCategory"
    )
    # { 'pl': "...", 'en': "...", ... }
    visibility = models.PositiveSmallIntegerField(
        choices=ProductVisibility.choices(), blank=False, null=False, default=ProductVisibilityEnum.UNKNOWN
    )
    magento_pk = models.IntegerField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    is_enabled = models.BooleanField(default=False)
    inherit_attributes = models.BooleanField(default=False)
    inherit_descriptions = models.BooleanField(default=False)
    inherit_images = models.BooleanField(default=False)
    db_created = models.DateTimeField(auto_now_add=True)
    db_modified = models.DateTimeField(auto_now=True)
    # Quality-gap rollup (pim-quality-score). Written ONLY via
    # Product.objects.filter(pk=...).update(...) — never instance.save() (signal loop).
    gap_worst_severity = models.CharField(  # noqa: DJ001 — NULL = no gaps / not evaluated
        max_length=16, choices=GapSeverity.choices, null=True, blank=True, db_index=True
    )
    gap_count = models.IntegerField(default=0)
    gap_evaluated_at = models.DateTimeField(null=True, blank=True)
    objects = ProductManager()

    #
    # Inheritance
    #
    @property
    def as_child(self):
        if self.product_class == ProductClassEnum.ProductBase:
            return self
        return getattr(self, ProductClass.labelFromId(self.product_class).lower())

    @property
    def product_class_name(self):
        return ProductClass.labelFromId(self.product_class)

    @property
    def visibility_name(self):
        return ProductVisibility.labelFromId(self.visibility)

    @property
    def name_t9n_json(self):
        try:
            name = self.products_attributes.get(
                feature__idx=SYSTEM_FEATURE_NAME_IDX, feature__scope=FeatureScopeEnum.SYSTEM
            )
        except ObjectDoesNotExist:
            return {}
        return name.value_txt_t9n

    @property
    def name(self):
        return self.name_lang(
            lang=self.shop.default_language.iso2 if IS_DEFAULT_LANG_FOR_CHANNELS_FROM_PIM else T9N_DEFAULT_LANG
        )

    def name_lang(self, lang):
        # .first() not .get(): a duplicate name row (leaky NULL-attribute constraint,
        # see migration cleaning django_pim_productattribute) must not raise
        # MultipleObjectsReturned and take down the whole product list.
        name = (
            self.products_attributes.filter(
                feature__idx=SYSTEM_FEATURE_NAME_IDX, feature__scope=FeatureScopeEnum.SYSTEM
            )
            .order_by("id")
            .first()
        )
        if name is None:
            return self.sku
        langs = [lang]

        added_lang = self.shop.default_language.iso2 if IS_DEFAULT_LANG_FOR_CHANNELS_FROM_PIM else T9N_DEFAULT_LANG
        if lang != added_lang:
            langs.append(added_lang)

        for lang in langs:
            if lang in name.value_txt_t9n:
                val = name.value_txt_t9n[lang]
                if val is not None:
                    val = str(val)
                    val = val.strip()
                    if len(val) > 0:
                        return val
        return self.sku

    @property
    def url_key(self):
        return self.url_key_lang(lang=T9N_DEFAULT_LANG)

    def url_key_lang(self, lang):
        url_key = self.products_attributes.get(
            feature__idx=SYSTEM_FEATURE_URL_KEY_IDX, feature__scope=FeatureScopeEnum.SYSTEM
        )
        langs = [lang]
        if lang != T9N_DEFAULT_LANG:
            langs.append(T9N_DEFAULT_LANG)
        for lang in langs:
            if lang in url_key.value_txt_t9n:
                val = url_key.value_txt_t9n[lang]
                if val is not None:
                    val = str(val)
                    val = val.strip()
                    if len(val) > 0:
                        return val
        return self.sku

    def description_lang(self, lang):
        return self.attribute_t9n(SYSTEM_FEATURE_DESCRIPTION_IDX, lang, FeatureScopeEnum.SYSTEM)

    def short_description_lang(self, lang):
        return self.attribute_t9n(SYSTEM_FEATURE_SHORT_DESCRIPTION_IDX, lang, FeatureScopeEnum.SYSTEM)

    def get_volume(self) -> Decimal | None:
        """Return product volume from the system 'volume' feature (DECIMAL type), or None."""
        try:
            attr = self.products_attributes.get(
                feature__idx=SYSTEM_FEATURE_VOLUME_IDX, feature__scope=FeatureScopeEnum.SYSTEM
            )
        except ObjectDoesNotExist:
            return None
        return attr.value_decimal

    def attribute_t9n(
        self, feature_idx: str, lang: str = T9N_DEFAULT_LANG, feature_scope: int = FeatureScopeEnum.BUSINESS_UNIT
    ) -> str:
        try:
            attribute = self.products_attributes.get(feature__idx=feature_idx, feature__scope=feature_scope)
        except Exception:
            return ""
        if lang not in attribute.value_txt_t9n:
            return ""
        val = attribute.value_txt_t9n[lang]
        if val is None:
            return ""
        return val

    def generate_url_key(self, lang: str, max_length=200, append_sku=True):
        url_key = slugify(self.name_lang(lang=lang))
        if append_sku:
            return "%s-%s" % (url_key[: max_length - len(self.sku)], str(self.sku))
        else:
            return url_key[:max_length]

    def generate_url_key_hashed(self, lang: str, max_length=200):
        hash_len = 6
        url_key = self.generate_url_key(lang, max_length, append_sku=False)
        h = hashlib.md5(str(self.sku).lower().encode("utf-8")).hexdigest()[:hash_len]
        return f"{url_key[: max_length - hash_len - 1]}-{h}"

    @property
    def thumb_picture(self):
        thumb_picture = self.pictures.filter(picture_role=PictureRoleEnum.MAIN).first()
        if thumb_picture is None:
            return None
        thumb_picture = thumb_picture.picture.picture_thumbs.all().first()
        if thumb_picture is None:
            return None
        return thumb_picture

    @property
    def main_picture(self):
        main_picture = self.pictures.filter(picture_role=PictureRoleEnum.MAIN).first()
        if main_picture is None:
            return None
        return main_picture.picture

    @property
    def main_product_picture(self):
        main_picture = self.pictures.filter(picture_role=PictureRoleEnum.MAIN).first()
        if main_picture is None:
            return None
        return main_picture

    @property
    def general_pictures(self):
        pics = []
        prod_pics = self.pictures.filter(picture_role=PictureRoleEnum.GENERAL).all().prefetch_related("picture")
        for prod_pic in prod_pics:
            pics.append(prod_pic.picture)
        return pics

    @property
    def subproducts_pictures(self):
        pics = []

        subproducts = self.subproducts.all()
        for subprod in subproducts:
            prod_pics = subprod.pictures.all().prefetch_related("picture")
            for prod_pic in prod_pics:
                if prod_pic.picture not in pics:
                    pics.append(prod_pic.picture)
        return pics

    @property
    def sku(self):
        return self.real_product.sku

    # cache aby szybciej renderowac view
    def get_breadcrumb_list(self, lang="en"):
        if self.category_id is None:
            return []
        key = "cat-%s-%s" % (self.category_id, lang)
        val = cache.get(key)
        if val is None:
            val = []
            for category in self.category.get_breadcrumb_list():
                if lang == "pl":
                    val.append([category.id, category.get_name_pl])
                else:
                    val.append([category.id, category.name_en])
            ttl = 60 * 60  # 1h
            cache.set(key, val, ttl)
        return val

    # id -> str

    def get_breadcrumb_simple(self, lang="en"):
        category_id = None
        txt = []
        for category_id, name in self.get_breadcrumb_list(lang=lang):
            txt.append(name)
        return category_id, " / ".join(txt)

    def get_product_attributes(self):
        products_attributes = (
            self.products_attributes.filter(feature__scope=FeatureScopeEnum.BUSINESS_UNIT)
            .exclude(feature__feature_type=FeatureTypeEnum.UNKNOWN)
            .prefetch_related("feature", "attribute")
        )
        return products_attributes

    def get_product_attributes_values(self, lang=None):
        products_attributes = (
            self.products_attributes.all()
            .exclude(feature__feature_type=FeatureTypeEnum.UNKNOWN)
            .prefetch_related("feature", "attribute")
        )
        values = {}
        for pa in products_attributes:
            if pa.feature.feature_type == FeatureTypeEnum.MULTISELECT:
                if pa.feature.idx not in values:
                    values[pa.feature.idx] = []
                values[pa.feature.idx].append(pa.get_value(lang=lang))
            else:
                values[pa.feature.idx] = pa.get_value(lang=lang)
        return values

    def __str__(self):
        return f"[{self.shop.idx}] {self.name} - {self.real_product.sku}"

    class Meta:
        ordering = ["id"]
        verbose_name_plural = "products"
        unique_together = ("real_product", "shop")
        indexes = [models.Index(fields=["real_product", "id"], name="idx_product_realproduct")]

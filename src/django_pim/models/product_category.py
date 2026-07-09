# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import hashlib

from django.conf import settings
from django.db import models
from django.db.models.constraints import UniqueConstraint
from idx_normalizator import normalize_url_key, validate_idx, validate_url_key
from slugify import slugify

from django_pim.settings import IS_DEFAULT_LANG_FOR_CHANNELS_FROM_PIM, T9N_DEFAULT_LANG


class ProductCategoryManager(models.Manager):
    def get_shop_root_categories(self, shop):
        query = self.model.objects.filter(shop=shop, tree_deep=0)
        return query


class ProductCategory(models.Model):
    # max_length of idx field
    MIN_IDX_LENGTH = 1
    MAX_IDX_LENGTH = 128
    URL_KEY_SEPARATOR = "-"

    shop = models.ForeignKey(
        "Channel",
        related_name="products_categories",
        verbose_name="shop",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )
    parent_category = models.ForeignKey(
        "self",
        related_name="subcategories",
        verbose_name="parent_category",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    # idx moze byc uzywane jako url_key w Magento dla store_code=all
    idx = models.CharField(max_length=128, blank=False, null=False)
    external_id = models.CharField(max_length=128, blank=True, null=True)
    url_key_t9n = models.JSONField(null=False, blank=True, default=dict)
    name_t9n = models.JSONField(null=False, default=dict)
    # NOT the storefront category description (description_t9n below) — internal AI/operator hint.
    desc = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Internal description / instruction. Used to ground AI workflows when matching "
            "(feature-set selection, attribute fill). Not shown on the storefront."
        ),
    )
    description_t9n = models.JSONField(null=False, default=dict)
    meta_title_t9n = models.JSONField(null=False, default=dict)
    meta_description_t9n = models.JSONField(null=False, default=dict)
    canonical_url_t9n = models.JSONField(null=False, default=dict, blank=True)
    image_url = models.CharField(max_length=512, blank=True, default="")
    og_image_url = models.CharField(max_length=512, blank=True, default="")
    noindex = models.BooleanField(default=False)
    nofollow = models.BooleanField(default=False)
    tree_deep = models.IntegerField(db_index=True, blank=True, null=False)
    position = models.IntegerField(db_index=True, blank=True, null=True)
    is_active = models.BooleanField(default=False)
    is_in_menu = models.BooleanField(default=False)
    rich_content = models.JSONField(null=True, blank=True)
    extension = models.JSONField(null=True, blank=True)
    db_created = models.DateTimeField(auto_now_add=True)
    db_modified = models.DateTimeField(auto_now=True)
    objects = ProductCategoryManager()

    @property
    def name(self):
        return self.name_lang(
            lang=self.shop.default_language.iso2 if IS_DEFAULT_LANG_FOR_CHANNELS_FROM_PIM else T9N_DEFAULT_LANG
        )

    def name_lang(self, lang, any_lang_if_missing=False):
        langs = [lang]
        added_lang = self.shop.default_language.iso2 if IS_DEFAULT_LANG_FOR_CHANNELS_FROM_PIM else T9N_DEFAULT_LANG
        if lang != added_lang:
            langs.append(added_lang)
        for lang in langs:
            if lang in self.name_t9n:
                name = self.name_t9n[lang]
                if name is not None:
                    name = str(name)
                    name = name.strip()
                    if len(name) > 0:
                        return name
        if any_lang_if_missing:
            try:
                langs = sorted(list(self.name_t9n.keys()))
                for lang in langs:
                    name = str(self.name_t9n[lang])
                    name = name.strip()
                    if name:
                        return name
            except:
                pass
        return self.idx

    @property
    def url_key(self):
        """Storefront routing slug for the channel's default language (same resolution Matrix routes by). Falls back to idx; read-only, never mutates."""
        lang = self.shop.default_language.iso2 if IS_DEFAULT_LANG_FOR_CHANNELS_FROM_PIM else T9N_DEFAULT_LANG
        return self.url_key_t9n.get(lang) or self.idx

    @property
    def description(self):
        return self.description_lang(lang=settings.T9N_DEFAULT_LANG)

    def description_lang(self, lang, any_lang_if_missing=False):
        langs = [lang]
        if lang != settings.T9N_DEFAULT_LANG:
            langs.append(settings.T9N_DEFAULT_LANG)
        for lang in langs:
            if lang in self.description_t9n:
                description = self.description_t9n[lang]
                if description is not None:
                    description = str(description)
                    description = description.strip()
                    if len(description) > 0:
                        return description
        if any_lang_if_missing:
            try:
                langs = sorted(list(self.description_t9n.keys()))
                for lang in langs:
                    description = str(self.description_t9n[lang])
                    description = description.strip()
                    if description:
                        return description
            except:
                pass
        return self.idx

    def normalize_idx(idx):
        """ "idx" is our default "url_key" so im using normalize_url_key()"""
        if idx is None:
            raise Exception('ProductCategory "idx" can not be None')
        return ProductCategory.normalize_url_key(idx)

    def validate_idx(idx):
        """Deprecated"""
        validate_idx(str(idx))

    def normalize_url_key(url_key):
        """Deprecated"""
        return normalize_url_key(url_key)

    def validate_url_key(url_key):
        """Deprecated"""
        validate_url_key(url_key)

    def validate_url_key_t9n(url_key_t9n):
        for lang, url_key in url_key_t9n.items():
            ProductCategory.validate_url_key(url_key)
            if lang is None or len(lang) != 2:
                raise Exception(f"Invalid lang in url_key_t9n={url_key_t9n}")
            if url_key is None or len(lang) != 2:
                raise Exception(f"Invalid url_key for lang={lang} in url_key_t9n={url_key_t9n}")

    def get_breadcrumb_list(self):
        if self.parent_category is None:
            return [self]
        else:
            rv = self.parent_category.get_breadcrumb_list()
            rv.append(self)
            return rv

    @property
    def breadcrumb_path(self):
        return self.get_breadcrumb_path()

    def get_breadcrumb_path(self, separator=None):
        if separator is None:
            separator = " > "
        rv = []
        for categ in self.get_breadcrumb_list():
            rv.append(categ.name)
        return separator.join(rv)

    def idx_path(self):
        if self.parent_category is None:
            return []
        idx_path = self.parent_category.idx_path()
        idx_path.append(self.idx)
        return idx_path

    def url_path(self, lang):
        if self.parent_category is None:
            return []
        url_path = self.parent_category.url_path(lang)
        url_path.append(self.url_key_lang(lang))
        return url_path

    def generate_url_key(self, lang):
        # generuje url_key na podstawie nazwy
        name = self.name_lang(lang=lang)
        MAX = 48  # magento przyjmuje max ? niech bedzie 48
        HASHLEN = 4  # dlugosc hasha
        # zamieniam pewne znaki specjalne
        name = name.replace("+", "plus")
        name = slugify(name, separator=ProductCategory.URL_KEY_SEPARATOR)
        if len(name) > MAX:
            prefix = name[: MAX - HASHLEN - 1]
            rest = name[MAX - HASHLEN - 1 :]
            rest = rest.encode("utf-8")
            m = hashlib.md5()
            m.update(rest)
            h = m.hexdigest()
            prefix = prefix.strip(ProductCategory.URL_KEY_SEPARATOR)
            name = "%s%s%s" % (prefix, ProductCategory.URL_KEY_SEPARATOR, h[:HASHLEN])
        return name

    def url_key_lang(self, lang):
        if lang not in self.url_key_t9n:
            self.url_key_t9n[lang] = self.generate_url_key(lang)
            self.save()
        return self.url_key_t9n[lang]

    @property
    def has_childs(self):
        if self.subcategories.all().count() > 0:
            return True
        return False

    @property
    def all_childs(self):
        return self.subcategories.all()

    def save(self, *args, **kwargs):
        self.url_key_t9n = dict(self.url_key_t9n)
        self.name_t9n = dict(self.name_t9n)
        self.description_t9n = dict(self.description_t9n)
        self.canonical_url_t9n = dict(self.canonical_url_t9n)
        ProductCategory.validate_idx(self.idx)
        ProductCategory.validate_url_key_t9n(self.url_key_t9n)
        if self.parent_category is None:
            self.tree_deep = 0
        else:
            self.tree_deep = self.parent_category.tree_deep + 1
        super().save(*args, **kwargs)

    def __str__(self):
        rv = []
        for categ in self.get_breadcrumb_list():
            rv.append(categ.name)
        return f"[{self.shop.idx}] " + " > ".join(rv)

    class Meta:
        ordering = ["idx"]
        verbose_name_plural = "products categories"
        constraints = [UniqueConstraint(fields=["shop", "idx"], name="Products_Categories_unique_idx")]

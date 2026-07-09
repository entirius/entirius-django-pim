# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import re

from django.db import models, transaction
from idx_normalizator import normalize_idx, validate_idx

IDX_ALLOWED_CHARS_PATTERN = re.compile(r"[^-a-z0-9_]+")


class ChannelManager(models.Manager):
    def availability_table(self, print_out=True):
        all_objects = self.all()
        tpl = "| {:<60} | {:<60} | {:<8} |"
        tpl_all = "| {:<143} |"
        tpl_row = tpl.replace("|", "+")
        tpl_row = tpl_row.replace(":", ":-")
        tpl_row = tpl_row.replace(" ", "-")
        tpl_row = tpl_row.format("", "", "", "", "")

        txts = ["Available channels:", tpl_row, tpl.format("idx", "name", "langs"), tpl_row]
        for obj in all_objects:
            langs = []
            for l in obj.languages.all():
                langs.append(l.iso2)
            txts.append(tpl.format(obj.idx, obj.name, ", ".join(langs)))
        if len(all_objects) == 0:
            txts.append(tpl_all.format("no channels are available"))
        txts.append(tpl_row)
        txt = "\n".join(txts)
        if print_out:
            print("\n" + txt, flush=True)
        return txt


class Channel(models.Model):
    idx = models.CharField(max_length=128, blank=False, null=False, unique=True)
    name = models.CharField(max_length=128, blank=False, null=False, default="", unique=True)
    default_language = models.ForeignKey(
        "django_regional.Language",
        related_name="pim_default_channels",
        verbose_name="default_language",
        help_text="Język domyślny nazw 'All Store Views' w Adminie Magento",
        null=False,
        blank=False,
        on_delete=models.PROTECT,
    )
    default_currency = models.ForeignKey(
        "django_regional.Currency",
        related_name="pim_default_channels",
        verbose_name="default_currency",
        help_text="",
        null=False,
        blank=False,
        on_delete=models.PROTECT,
    )
    languages = models.ManyToManyField(
        "django_regional.Language",
        related_name="pim_channels",
        verbose_name="languages",
        blank=True,
        db_table="django_pim_shop_languages",
    )
    currencies = models.ManyToManyField(
        "django_regional.Currency",
        related_name="pim_channels",
        verbose_name="currencies",
        blank=True,
        db_table="django_pim_shop_currencies",
    )
    is_default = models.BooleanField(default=False)
    inheritance_enabled = models.BooleanField(default=False)
    default_inheritance_flags = models.JSONField(default=list, blank=True)
    objects = ChannelManager()

    VALID_INHERITANCE_FLAGS = {"attributes", "descriptions", "images"}

    @staticmethod
    def normalize_idx(idx):
        """Deprecated"""
        return normalize_idx(idx)

    @staticmethod
    def validate_idx(idx):
        """Deprecated"""
        validate_idx(idx)

    @property
    def idx_path(self):
        return f"{self.idx}"

    def resolve_language(self, params: dict):
        lang = params.get("lang", None)
        if lang is None:
            lang = self.default_language.iso2
            lang = lang.lower()

        return lang

    def resolve_currency(self, params: dict):
        curr = params.get("currency", None)
        if curr is None:
            curr = self.default_currency.iso3

        return curr

    def save(self, *args, **kwargs):
        Channel.validate_idx(self.idx)
        # Validate default_inheritance_flags
        if self.default_inheritance_flags:
            invalid = set(self.default_inheritance_flags) - self.VALID_INHERITANCE_FLAGS
            if invalid:
                raise ValueError(f"Invalid inheritance flags: {invalid}. Valid values: {self.VALID_INHERITANCE_FLAGS}")
        if self.is_default:
            with transaction.atomic():
                Channel.objects.exclude(pk=self.pk).filter(is_default=True).update(is_default=False)
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)
        if self.default_language is not None:
            self.languages.add(self.default_language)
        if self.default_currency is not None:
            self.currencies.add(self.default_currency)

    def delete(self, *args, **kwargs):
        if self.is_default:
            raise models.ProtectedError("Cannot delete the default channel.", [self])
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.name} [{self.idx}]"

    class Meta:
        db_table = "django_pim_shop"
        ordering = []
        verbose_name_plural = "channels"


# Backward-compatible aliases
ShopManager = ChannelManager
Shop = Channel

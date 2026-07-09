# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.contrib import admin
from django.db.models import Q
from django.utils.safestring import mark_safe
from django_admin_inline_paginator.admin import TabularInline

from .admin_actions.feature import (
    make_comparable,
    make_filterable,
    make_for_customization,
    make_invisible,
    make_not_comparable,
    make_not_filterable,
    make_not_for_customization,
    make_not_required,
    make_not_searchable,
    make_required,
    make_searchable,
    make_visible,
)
from .filters.admin.feature_type_filter import FeatureTypeFilter
from .models import *
from .settings import SYSTEM_FEATURE_NAME_IDX, T9N_DEFAULT_LANG


class ChannelAdmin(admin.ModelAdmin):
    list_display = ("idx",)
    search_fields = ["idx"]
    ordering = ("idx",)


class PimSettingsAdmin(admin.ModelAdmin):
    list_display = ("matrix_signals_enabled", "gaps_enabled", "gaps_rules_changed_at", "gaps_recomputed_at")
    readonly_fields = ("gaps_rules_changed_at", "gaps_recomputed_at")

    def has_add_permission(self, request):
        return not PimSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from django.core.cache import cache

        cache.delete("pim:matrix_signals_enabled")
        cache.delete("pim:gaps_enabled")


class ProductPictureAdmin(admin.ModelAdmin):
    list_display = ("image_tag", "product", "picture_role", "position", "language", "alt_text_t9n")
    search_fields = ["product__real_product__sku"]
    list_filter = ["picture_role", "language", "product__shop", "product__product_class"]
    autocomplete_fields = ["product", "picture"]

    def image_tag(self, obj):
        if not obj.picture.image:
            return "no pic"
        return mark_safe('<img src="%s" width="auto" height="60px" />' % obj.picture.image.url)

    image_tag.short_description = "Image"


class ProductAttributeImageAdmin(admin.ModelAdmin):
    list_display = ("product", "attribute", "picture", "color_hash")
    list_filter = ["product__shop", "attribute__feature", "attribute__group", "product__product_class"]
    search_fields = ["product__real_product__sku", "attribute__idx", "picture__sha1", "color_hash"]
    readonly_fields = ["product", "attribute", "picture"]


class AttributeInline(admin.TabularInline):
    model = ProductAttributeCustomImage.attributes.through
    extra = 1


class ProductAttributeCustomImageAdmin(admin.ModelAdmin):
    inlines = [AttributeInline]
    autocomplete_fields = ["product", "picture"]
    exclude = ("attributes",)


class ProductCategoryPictureAdmin(admin.ModelAdmin):
    list_display = ("image_tag", "product_category", "picture_role")
    search_fields = ["picture_role", "product_category__idx", "product_category"]
    readonly_fields = ["product_category", "picture"]
    ordering = ("product_category__id", "picture_role")

    def image_tag(self, obj):
        if not obj.picture.image:
            return "no pic"
        return mark_safe('<img src="%s" width="auto" height="60px" />' % obj.picture.image.url)


class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "idx",
        "name",
        "parent_category",
        "url_key_t9n",
        "tree_deep",
        "shop",
        "position",
        "is_active",
        "is_in_menu",
        "image_tag",
        "extension",
    )
    search_fields = ["idx", "name_t9n", "url_key_t9n", "meta_title_t9n", "meta_description_t9n"]
    ordering = ("tree_deep", "parent_category__name_t9n__pl", "name_t9n__pl")
    list_filter = ("shop", "is_active", "is_in_menu", "tree_deep")
    readonly_fields = ("parent_category",)

    def image_tag(self, obj):
        pic = obj.pictures.first()
        if pic is None:
            return "no pic"
        if not pic.picture.image:
            return "no pic"
        return mark_safe('<img src="%s" width="auto" height="60px" />' % pic.picture.image.url)


class ProductInCategoryAdmin(admin.ModelAdmin):
    list_display = ("product", "category", "position", "updated_at")
    search_fields = ["product__real_product__sku", "category__name_t9n__pl"]
    list_filter = ("category__shop", "category")
    autocomplete_fields = ["product", "category"]


class ProductSimpleAdmin(admin.ModelAdmin):
    list_display = (
        "real_product",
        "shop",
        "feature_set",
        "quantity",
        "visibility",
        "is_enabled",
        "db_created",
        "db_modified",
        "updated_at",
    )
    exclude = []
    search_fields = ["real_product__sku"]
    list_filter = ("shop", "feature_set", "visibility", "is_enabled")
    readonly_fields = ["real_product", "product_class", "feature_set", "shop"]
    ordering = ("id",)


class ProductConfigurableAdmin(admin.ModelAdmin):
    list_display = (
        "real_product",
        "shop",
        "feature_set",
        "visibility",
        "is_enabled",
        "db_created",
        "db_modified",
        "updated_at",
    )
    exclude = []
    list_filter = ("shop", "feature_set", "visibility", "is_enabled")
    readonly_fields = ["real_product", "product_class", "feature_set", "shop"]
    search_fields = ["configurable_links__product_configurable__real_product__sku"]
    ordering = ("id",)


class ProductBundleAdmin(admin.ModelAdmin):
    list_display = (
        "real_product",
        "shop",
        "feature_set",
        "visibility",
        "is_enabled",
        "db_created",
        "db_modified",
        "updated_at",
    )
    exclude = []
    list_filter = ("shop", "feature_set", "visibility", "is_enabled")
    readonly_fields = ["real_product", "product_class", "feature_set", "shop"]
    ordering = ("id",)
    search_fields = ["bundle_links__product_bundle__real_product__sku"]


class ProductCustomAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "shop",
        "feature_set",
        "customization_feature_set",
        "visibility",
        "is_enabled",
        "db_created",
        "db_modified",
        "source_product",
    )
    exclude = []
    list_filter = ("shop", "feature_set", "customization_feature_set", "visibility", "is_enabled")
    readonly_fields = ["real_product", "product_class", "feature_set", "shop"]
    ordering = ("id",)
    search_fields = ["real_product__sku", "real_product__ean", "source_product__real_product__sku"]
    autocomplete_fields = ["source_product"]
    list_select_related = (
        "real_product",
        "shop",
        "feature_set",
        "customization_feature_set",
        "source_product__real_product",
    )

    def sku(self, obj):
        return obj.real_product.sku

    sku.admin_order_field = "real_product__sku"
    sku.short_description = "SKU"


class RealProductAdmin(admin.ModelAdmin):
    list_display = ("sku", "ean", "weight", "width", "height", "deep", "kind_of_product")
    search_fields = ["sku", "ean"]
    exclude = []
    readonly_fields = ["sku"]
    ordering = ("sku",)


class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "sku",
        "name",
        "magento_pk",
        "shop",
        "feature_set",
        "product_class",
        "kind_of_product",
        "is_enabled",
        "db_created",
        "db_modified",
    )
    search_fields = ["real_product__sku", "real_product__ean"]
    exclude = []
    list_filter = ("shop", "product_class", "is_enabled", "real_product__kind_of_product", "feature_set")
    autocomplete_fields = ["real_product"]
    ordering = ("id",)

    def sku(self, obj):
        return obj.real_product.sku

    sku.admin_order_field = "real_product__sku"
    sku.short_description = "SKU"

    def kind_of_product(self, obj):
        return obj.real_product.kind_of_product_name

    kind_of_product.admin_order_field = "real_product__kind_of_product"

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if search_term:
            queryset |= self.model.objects.filter(
                Q(**{f"products_attributes__value_txt_t9n__{T9N_DEFAULT_LANG}__icontains": search_term})
                & Q(products_attributes__feature__idx=SYSTEM_FEATURE_NAME_IDX)
            )

        # Zamiast stosować distinct na konkretnych polach, użyj zwykłego distinct()
        # i ustaw use_distinct na True
        return queryset.distinct(), True


class ProductPriceAdmin(admin.ModelAdmin):
    list_display = ("product", "price_brutto", "currency", "special_price", "special_price_from", "special_price_to")
    readonly_fields = ("product", "currency")
    search_fields = ["product__real_product__sku"]


class ProductLinkTypeAdmin(admin.ModelAdmin):
    list_display = ("idx", "name_t9n", "position")
    search_fields = ["idx", "name_t9n"]
    ordering = ("position", "idx")


class ProductLinkAdmin(admin.ModelAdmin):
    list_display = ("product", "linked_product", "link_type", "position")
    readonly_fields = ("product", "linked_product", "link_type", "position")
    autocomplete_fields = ["link_type"]


class FeatureSetAdmin(admin.ModelAdmin):
    list_display = ("idx", "name", "magento_idx", "magento_pk", "is_default")
    search_fields = ["idx", "name_t9n"]
    ordering = ("idx",)


class FeatureInFeatureSetAdmin(admin.ModelAdmin):
    list_display = ("feature_set", "feature", "position")
    search_fields = ["feature_set__idx", "feature__idx"]
    list_filter = ("feature_set", "feature")
    ordering = ("feature_set", "position")


class FeatureInFeatureSetInline(TabularInline):
    model = FeatureInFeatureSet
    fields = ["feature_set", "position"]
    per_page = 100
    extra = 0


class FeatureAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "scope",
        "idx",
        "feature_type",
        "magento_idx",
        "magento_pk",
        "name",
        "is_required",
        "is_visible",
        "is_filterable",
        "is_searchable",
        "is_comparable",
        "is_for_customization",
        "filter_type",
        "frontend_input_type",
        "display_order",
    )
    inlines = [FeatureInFeatureSetInline]
    search_fields = ["idx", "magento_idx", "name_t9n"]
    ordering = ("pk",)
    list_filter = (
        "features_sets",
        "scope",
        "feature_type",
        "is_required",
        "is_visible",
        "is_filterable",
        "is_searchable",
        "is_comparable",
        "is_for_customization",
    )
    actions = [
        make_visible,
        make_invisible,
        make_required,
        make_not_required,
        make_filterable,
        make_not_filterable,
        make_searchable,
        make_not_searchable,
        make_comparable,
        make_not_comparable,
        make_for_customization,
        make_not_for_customization,
    ]


class AttributeAdmin(admin.ModelAdmin):
    list_display = ("idx", "feature", "magento_idx", "magento_pk", "name", "display_order")
    list_filter = ("feature",)
    search_fields = ["idx", "magento_idx", "name_t9n"]


class AttributeModifierAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "attributes_list",
        "csv_row_hash",
        "product",
        "real_product",
        "feature",
        "groups_list",
        "attribute_modified",
        "feature_modified",
        "modifier_type",
        "value_modifier",
        "source_id",
    )
    search_fields = ["feature__idx", "feature_modified__idx", "product__real_product__sku", "real_product__sku"]
    ordering = ("feature_modified__idx",)
    autocomplete_fields = ("attributes", "feature", "groups", "feature_modified", "attribute_modified", "product")
    list_filter = (
        "modifier_type",
        "product__shop",
        ("attributes__feature", admin.RelatedOnlyFieldListFilter),
        ("feature_modified", admin.RelatedOnlyFieldListFilter),
        ("attribute_modified", admin.RelatedOnlyFieldListFilter),
        ("attribute_coerced", admin.RelatedOnlyFieldListFilter),
        ("product", admin.RelatedOnlyFieldListFilter),
        ("real_product", admin.RelatedOnlyFieldListFilter),
        ("attributes", admin.RelatedOnlyFieldListFilter),
    )

    def attributes_list(self, obj):
        return ", ".join([str(a.idx) for a in obj.attributes.all()])

    def groups_list(self, obj):
        return ", ".join([str(a.idx) for a in obj.groups.all()])


class PictureDownloadUrlAdmin(admin.ModelAdmin):
    list_display = ("picture", "url", "db_created")
    readonly_fields = ("picture", "url", "db_created")
    search_fields = ["picture__image", "picture__sha1"]


class PictureAdmin(admin.ModelAdmin):
    list_display = ("image_tag", "image", "sha1", "width", "height", "db_created")
    search_fields = ["image", "sha1", "db_created"]
    readonly_fields = ("sha1", "image", "width", "height")

    def image_tag(self, obj):
        if not obj.image:
            return "no pic"
        return mark_safe('<img src="%s" width="auto" height="60px" />' % obj.image.url)

    image_tag.short_description = "Image"


class ProductAttributeAdmin(admin.ModelAdmin):
    model = ProductAttribute
    list_display = (
        "id",
        "product",
        "feature",
        "print_value",
        "attribute",
        "value_bool",
        "value_decimal",
        "value_datetime",
        "shop_idx",
    )
    list_filter = (
        "feature",
        "feature__feature_type",
        "feature__is_for_customization",
        "product__shop",
        "product__product_class",
        "attribute",
    )
    autocomplete_fields = ("product", "feature", "attribute")
    search_fields = ["product__real_product__sku"]
    readonly_fields = []
    fieldsets = (
        (None, {"fields": ("product", "feature", "attribute")}),
        (
            "Value",
            {"fields": ("value_bool", "value_decimal", "value_datetime", "value_txt", "value_txt_t9n", "value_json")},
        ),
        ("Translations", {"fields": []}),
    )

    def add_language_methods(self, obj):
        if obj and hasattr(obj, "value_txt_t9n") and isinstance(obj.value_txt_t9n, dict):
            for lang in obj.value_txt_t9n.keys():
                method = self.create_language_display_method(lang)
                setattr(self, f"value_txt_t9n_display_{lang}", method)

    def create_language_display_method(self, lang):
        def display_method(obj):
            if obj and hasattr(obj, "value_txt_t9n") and obj.value_txt_t9n and lang in obj.value_txt_t9n:
                return obj.value_txt_t9n[lang]
            return "No translation available"

        display_method.short_description = f"Language: {lang}"
        return display_method

    def shop_idx(self, obj):
        return obj.product.shop.idx

    def print_value(self, obj):
        feature_type = obj.feature.feature_type_name
        value = obj.get_value(langs=[obj.product.shop.default_language.iso2])
        value = str(value)
        value = value[:128]
        return f"{feature_type}:{value}"

    print_value.short_description = "Value"

    def get_readonly_fields(self, request, obj=None):
        self.add_language_methods(obj)
        readonly_fields = super().get_readonly_fields(request, obj)
        if obj and hasattr(obj, "value_txt_t9n") and isinstance(obj.value_txt_t9n, dict):
            for lang in obj.value_txt_t9n.keys():
                readonly_fields.append(f"value_txt_t9n_display_{lang}")
        return readonly_fields

    def get_fieldsets(self, request, obj=None):
        self.add_language_methods(obj)
        fieldsets = super().get_fieldsets(request, obj)
        if obj and hasattr(obj, "value_txt_t9n") and isinstance(obj.value_txt_t9n, dict):
            translations_fields = [f"value_txt_t9n_display_{lang}" for lang in obj.value_txt_t9n.keys()]
            fieldsets[-1][1]["fields"] = translations_fields
        return fieldsets


class ThumbAdmin(admin.ModelAdmin):
    list_display = ("image_tag", "image", "width", "height", "db_created")
    search_fields = ["sha1", "db_created"]
    readonly_fields = ("sha1", "image", "width", "height")

    def image_tag(self, obj):
        if not obj.image:
            return "no pic"
        return mark_safe('<img src="%s" width="auto" height="60px" />' % obj.image.url)

    image_tag.short_description = "Image"


class PictureThumbAdmin(admin.ModelAdmin):
    list_display = ("image_tag", "thumb_tag", "picture", "thumb", "width", "height", "transform_method", "out_format")
    search_fields = ["picture__sha1", "thumb__sha1", "picture__products__product__real_product__sku"]
    readonly_fields = ("picture", "thumb", "width", "height", "transform_method", "out_format")
    list_filter = ("transform_method", "out_format")

    def image_tag(self, obj):
        if not obj.picture.image:
            return "no pic"
        return mark_safe('<img src="%s" width="auto" height="60px" />' % obj.picture.image.url)

    def thumb_tag(self, obj):
        if not obj.thumb.image:
            return "no pic"
        return mark_safe('<img src="%s" width="auto" height="60px" />' % obj.thumb.image.url)

    image_tag.short_description = "Source Picture"
    thumb_tag.short_description = "Picture Thumb"


# Product Configurable
class ConfigurableLinkAdmin(admin.ModelAdmin):
    list_display = ("product_configurable", "subproduct_attribute", "subproduct", "get_subproduct_feature_idx")
    readonly_fields = ("product_configurable", "subproduct_attribute", "subproduct")
    list_filter = ("product_configurable", "product_configurable__shop", "subproduct_attribute__feature")
    search_fields = ["product_configurable__real_product__sku", "subproduct__real_product__sku"]

    def get_subproduct_feature_idx(self, obj):
        return obj.subproduct_attribute.feature.idx

    get_subproduct_feature_idx.short_description = "Subproduct Feature IDX"


# Product Bundle
class BundleSectionAdmin(admin.ModelAdmin):
    list_display = ("idx", "name", "desc", "section_type")
    ordering = ("idx",)
    search_fields = ("idx", "name")


class BundleLinkAdmin(admin.ModelAdmin):
    list_display = (
        "product_bundle",
        "subproduct",
        "quantity",
        "section",
        "is_default",
        "is_required",
        "can_change_quantity",
    )
    autocomplete_fields = ("product_bundle", "subproduct", "section")
    search_fields = ["product_bundle__real_product__sku", "subproduct__real_product__sku"]


@admin.register(AttributesGroup)
class AttributesGroupAdmin(admin.ModelAdmin):
    list_display = ("idx", "name_t9n")
    search_fields = ["idx"]


class FilesDownloadUrlAdmin(admin.ModelAdmin):
    list_display = ("file", "url", "db_created")
    readonly_fields = ("file", "url", "db_created")
    search_fields = ["file__file", "file__sha1"]


class FilesAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "file",
        "file_category",
        "file_type",
        "codec",
        "file_label",
        "height",
        "weight",
        "width",
        "sha1",
        "original_file_name",
        "db_created",
    )
    list_filter = ("file_category", "file_type")
    search_fields = ["file", "sha1", "db_created"]


class FilesCategoryAdmin(admin.ModelAdmin):
    list_display = ("code", "name_t9n", "db_created")
    search_fields = ["code"]


class ProductFileAdmin(admin.ModelAdmin):
    list_display = ("product", "file", "get_file_category")
    search_fields = ["product__real_product__sku", "product__id"]
    list_filter = ["product__shop", "file__file_category", "product__product_class"]
    autocomplete_fields = ["product", "file"]

    def get_file_category(self, obj):
        return obj.file.file_category.code


class AttributePictureAdmin(admin.ModelAdmin):
    list_display = ("image_tag", "attribute", "picture")
    search_fields = ["attribute__idx"]
    list_filter = [FeatureTypeFilter]
    autocomplete_fields = ["attribute", "picture"]

    def image_tag(self, obj):
        if not obj.picture.image:
            return "no pic"
        return mark_safe('<img src="%s" width="auto" height="60px" />' % obj.picture.image.url)

    image_tag.short_description = "Image"


class VideoAdmin(admin.ModelAdmin):
    list_display = ("title", "video_url", "is_external", "source", "db_created", "db_modified")
    search_fields = ["title", "video_url"]
    list_filter = ("is_external", "source")


class ProductVideoAdmin(admin.ModelAdmin):
    list_display = ("product", "video", "video_role", "position", "language")
    search_fields = ["product__real_product__sku", "product__id", "video__video_url", "video__title"]
    list_filter = [
        "video_role",
        "language",
        "product__shop",
        "product__product_class",
        "video__source",
        "video__is_external",
    ]
    autocomplete_fields = ["product", "video"]


admin.site.register(Channel, ChannelAdmin)
admin.site.register(PimSettings, PimSettingsAdmin)
admin.site.register(ProductSimple, ProductSimpleAdmin)
admin.site.register(ProductConfigurable, ProductConfigurableAdmin)
admin.site.register(ProductBundle, ProductBundleAdmin)
admin.site.register(ProductCustom, ProductCustomAdmin)
admin.site.register(Product, ProductAdmin)
admin.site.register(RealProduct, RealProductAdmin)
admin.site.register(ProductPrice, ProductPriceAdmin)
admin.site.register(Picture, PictureAdmin)
admin.site.register(PictureThumb, PictureThumbAdmin)
admin.site.register(Thumb, ThumbAdmin)
admin.site.register(ProductCategory, ProductCategoryAdmin)
admin.site.register(ProductPicture, ProductPictureAdmin)
admin.site.register(ProductCategoryPicture, ProductCategoryPictureAdmin)
admin.site.register(ProductInCategory, ProductInCategoryAdmin)
admin.site.register(BundleLink, BundleLinkAdmin)
admin.site.register(BundleSection, BundleSectionAdmin)
admin.site.register(PictureDownloadUrl, PictureDownloadUrlAdmin)
admin.site.register(AttributePicture, AttributePictureAdmin)
admin.site.register(Video, VideoAdmin)
admin.site.register(ProductVideo, ProductVideoAdmin)

admin.site.register(FilesDownloadUrl, FilesDownloadUrlAdmin)
admin.site.register(Files, FilesAdmin)
admin.site.register(FilesCategory, FilesCategoryAdmin)
admin.site.register(ProductFile, ProductFileAdmin)

admin.site.register(Feature, FeatureAdmin)
admin.site.register(FeatureSet, FeatureSetAdmin)
admin.site.register(FeatureInFeatureSet, FeatureInFeatureSetAdmin)
admin.site.register(Attribute, AttributeAdmin)
admin.site.register(AttributeModifier, AttributeModifierAdmin)
admin.site.register(ProductAttribute, ProductAttributeAdmin)
admin.site.register(ProductLinkType, ProductLinkTypeAdmin)
admin.site.register(ProductLink, ProductLinkAdmin)

# Product Configurable
admin.site.register(ConfigurableLink, ConfigurableLinkAdmin)

admin.site.register(ProductAttributeImage, ProductAttributeImageAdmin)
admin.site.register(ProductAttributeCustomImage, ProductAttributeCustomImageAdmin)


# Quality gaps (pim-quality-score)
class GapDefinitionAdmin(admin.ModelAdmin):
    list_display = ("key", "check_key", "severity", "active", "display_order")
    list_filter = ("check_key", "severity", "active")
    search_fields = ["key"]
    ordering = ("display_order", "key")


class GapFindingAdmin(admin.ModelAdmin):
    list_display = ("product", "definition", "language", "severity", "inherited", "channel_idx")
    list_filter = ("severity", "inherited", "definition")
    search_fields = ["product__real_product__sku", "channel_idx"]
    raw_id_fields = ("product", "definition")
    readonly_fields = ("product", "channel_idx", "definition", "language", "severity", "inherited", "source_channel")

    def has_add_permission(self, request):
        return False


class GapExemptionAdmin(admin.ModelAdmin):
    list_display = ("product", "definition", "language", "reason", "created_by", "created_at")
    list_filter = ("definition",)
    search_fields = ["product__real_product__sku"]
    raw_id_fields = ("product", "definition")


admin.site.register(GapDefinition, GapDefinitionAdmin)
admin.site.register(GapFinding, GapFindingAdmin)
admin.site.register(GapExemption, GapExemptionAdmin)

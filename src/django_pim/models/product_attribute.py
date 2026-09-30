# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging
import math
from itertools import groupby

from django.db import models
from django.db.models import OuterRef, Subquery
from django_utils.api.responses import ErrorInfo

from django_pim import settings
from django_pim.models.attribute import Attribute, AttributeModifier, AttributeModifierTypeEnum
from django_pim.models.attributes_group import AttributesGroup
from django_pim.models.feature import Feature
from django_pim.models.feature_set import FeatureInFeatureSet
from django_pim.models.product_attribute_image import ProductAttributeImage
from django_pim.models.product_custom import ProductCustom

from .feature import FeatureScopeEnum, FeatureTypeEnum

logger_process = logging.getLogger("process")

from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import F, Prefetch, Q
from django_utils.managers.enhance_manager import EnhanceManager

from django_pim.settings import LIMITED_CUSTOM_FEATURES_IDXS_TO_VIEW


class WrongProductCustom(Exception):
    pass


class WrongCustomConfiguration(Exception):
    pass


class ProductAttributeManager(EnhanceManager):
    @staticmethod
    def iterate_over_attribute_modifiers(am, restricted_filter_query):
        for attr_idx, feature_idx, coerce_idx in am:
            filters = {}
            if feature_idx is not None:
                filters["feature__idx"] = feature_idx
            if attr_idx is not None:
                filters["idx"] = attr_idx
            restricted_filter_query.append(Q(**filters))
        return restricted_filter_query

    def get_global_restriction_query(self, product):
        restricted_filter_query = []
        default_filter_query = []
        coerce_filter_query = []
        # Wykluczenia globalne
        am = AttributeModifier.objects.filter(~Q(modifier_type=AttributeModifierTypeEnum.VALUE)).filter(
            Q(
                Q(
                    Q(product=product)
                    | Q(real_product=product.real_product)
                    | Q(Q(real_product__isnull=True) & Q(product__isnull=True))
                )
                & Q(attributes__isnull=True)
                & Q(groups__isnull=True)
                & Q(feature__isnull=True)
            )
        )

        restricted_filter_query = self.iterate_over_attribute_modifiers(
            am.filter(modifier_type=AttributeModifierTypeEnum.EXCLUDE).values_list(
                "attribute_modified__idx", "feature_modified__idx", "attribute_coerced__idx"
            ),
            restricted_filter_query,
        )
        default_filter_query = self.iterate_over_attribute_modifiers(
            am.filter(modifier_type=AttributeModifierTypeEnum.DEFAULT).values_list(
                "attribute_modified__idx", "feature_modified__idx", "attribute_coerced__idx"
            ),
            default_filter_query,
        )
        coerce_filter_query = self.iterate_over_attribute_modifiers(
            am.filter(modifier_type=AttributeModifierTypeEnum.COERCE).values_list(
                "attribute_modified__idx", "feature_modified__idx", "attribute_coerced__idx"
            ),
            coerce_filter_query,
        )
        return restricted_filter_query, default_filter_query, coerce_filter_query

    def get_restriction_query(self, attr_query, product):
        attr_idx_list = [idx["idx"] for data in attr_query.values() if isinstance(data, list) for idx in data]
        group_idx_list = [
            idx["group__idx"]
            for data in attr_query.values()
            if isinstance(data, list)
            for idx in data
            if "group__idx" in idx and idx["group__idx"] is not None
        ]
        am = (
            AttributeModifier.objects.filter(
                Q(
                    Q(product=product)
                    | Q(real_product=product.real_product)
                    | Q(Q(real_product__isnull=True) & Q(product__isnull=True))
                )
            )
            .filter_by_all_possible_attributes(attr_idx_list)
            .filter_by_all_possible_groups(group_idx_list)
            .order_by("product")
            .only("attribute_modified__idx", "feature_modified__idx", "modifier_type")
        )
        return am

    def get_restrictions_query_by_type(self, attr_query, product, filter_type, all_filter_query=None):
        if all_filter_query is None:
            all_filter_query = []
        am_all = []
        am = self.get_restriction_query(attr_query, product)
        am_all.extend(
            am.filter(modifier_type=filter_type).values_list(
                "attribute_modified__idx", "feature_modified__idx", "attribute_coerced__idx"
            )
        )
        all_filter_query = self.iterate_over_attribute_modifiers(am_all, all_filter_query)
        return all_filter_query, am_all

    def get_restriction_query_filters(self, attr_query, product, restricted_filter_query=None):
        if restricted_filter_query is None:
            restricted_filter_query = []

        am_filters = []
        am_value = []
        am = self.get_restriction_query(attr_query, product)
        am_filters.extend(
            am.filter(modifier_type=AttributeModifierTypeEnum.EXCLUDE).values_list(
                "attribute_modified__idx", "feature_modified__idx", "attribute_coerced__idx"
            )
        )
        am_value.extend(
            am.filter(modifier_type=AttributeModifierTypeEnum.VALUE)
            .select_related("feature_modified")
            .prefetch_related(
                Prefetch("attributes", queryset=Attribute.objects.order_by("idx")),
                Prefetch("groups", queryset=AttributesGroup.objects.order_by("idx")),
            )
        )

        restricted_filter_query = self.iterate_over_attribute_modifiers(am_filters, restricted_filter_query)
        return restricted_filter_query, am_value

    def unpack_nested_list(self, input_list):
        result = []
        for item in input_list:
            if isinstance(item, list):
                result.extend(self.unpack_nested_list(item))
            else:
                result.append(item)
        return result

    @staticmethod
    def _get_product_custom(sku, channel_idx):
        product_custom = (
            ProductCustom.objects.filter(real_product__sku=sku, shop__idx=channel_idx)
            .select_related("customization_feature_set")
            .first()
        )
        if not product_custom:
            raise WrongProductCustom("Product custom not found")

        return product_custom

    # django-checkout
    # django-matrix
    def get_custom_attributes_details(
        self, product_custom_sku, all_attr_modifier, channel_idx, language_iso2, limit_view=False
    ):

        t9n_filter = {f"value_txt_t9n__{language_iso2}__isnull": False}

        # get attributes specification for custom
        product_attr_specification_query = ProductAttribute.objects.filter(
            Q(Q(**t9n_filter) | ~Q(value_decimal=None))
            & Q(product__real_product__sku=product_custom_sku)
            & Q(product__shop__idx=channel_idx)
            & Q(feature__is_for_customization=True)
            & Q(
                feature__feature_type__in=[
                    FeatureTypeEnum.DECIMAL,
                    FeatureTypeEnum.TEMPERATURE,
                    FeatureTypeEnum.MASS,
                    FeatureTypeEnum.LENGTH,
                ]
            )
        ).select_related("product", "product__shop", "product__shop__default_language", "feature")
        custom_idxs = list(settings.CUSTOM_FEATURES_ADDITIONAL_DATA.keys())
        product_attr_custom_specification_query = Attribute.objects.filter(
            feature__is_for_customization=True, feature__idx__in=custom_idxs
        ).values_list("idx", "feature__idx")

        grouped_product_attr_custom_specification_query = {}
        for feature_idx, items in groupby(
            sorted(product_attr_custom_specification_query, key=lambda x: x[1]), key=lambda x: x[1]
        ):
            grouped_product_attr_custom_specification_query[feature_idx] = list(items)

        result_values_dict = {
            item.feature.idx: [
                item.get_value(language_iso2),
                item.feature.name_lang(language_iso2),
                item.feature.feature_type,
            ]
            for item in product_attr_specification_query
        }
        values_change = {}

        for attr_modifier in all_attr_modifier:
            added_attr = []
            default_unit, model_unit = attr_modifier.feature_modified.get_cls_unit_conversion()
            if attr_modifier.feature_modified.idx not in result_values_dict:
                result_values_dict[attr_modifier.feature_modified.idx] = [
                    model_unit(0, default_unit),
                    attr_modifier.feature_modified.name_lang(language_iso2),
                    attr_modifier.feature_modified.feature_type,
                    {},
                    attr_modifier.feature_modified.name_lang("en"),
                ]

            for feature, feature_idx_mod in settings.CUSTOM_FEATURES_ADDITIONAL_DATA.items():
                if not attr_modifier.feature_modified:
                    continue
                if feature_idx_mod != attr_modifier.feature_modified.idx:
                    continue
                if feature not in grouped_product_attr_custom_specification_query.keys():
                    continue
                feature_obj = Feature.objects.get(idx=feature)
                if not feature:
                    continue
                attrs = list(attr_modifier.attributes.all().values_list("idx", flat=True))

                attr_in_modifiers = []
                for idx, _ in list(grouped_product_attr_custom_specification_query[feature]):
                    if idx in attrs:
                        attr_in_modifiers.append(idx)

                if attr_in_modifiers:
                    if feature not in result_values_dict:
                        result_values_dict[feature] = [
                            model_unit(attr_modifier.value_modifier, default_unit),
                            feature_obj.name_lang(language_iso2),
                            attr_modifier.feature_modified.feature_type,
                            {attr_in_modifiers[0]: int(attr_modifier.value_modifier)},
                            feature_obj.name_lang("en"),
                        ]
                    else:
                        result_values_dict[feature][0] += model_unit(attr_modifier.value_modifier, default_unit)
                        result_values_dict[feature][3] = result_values_dict[feature][3] | {
                            attr_in_modifiers[0]: int(attr_modifier.value_modifier)
                        }

            if hasattr(attr_modifier.feature_modified, "idx"):
                calc_hash = hash(
                    tuple(
                        sorted(
                            list(attr_modifier.attributes.all().values_list("idx", flat=True))
                            + list(attr_modifier.groups.all().values_list("idx", flat=True))
                        )
                    )
                )
                if calc_hash in added_attr:
                    continue

                added_attr.append(calc_hash)
                if attr_modifier.feature_modified.idx not in values_change:
                    values_change[attr_modifier.feature_modified.idx] = []
                values_change[attr_modifier.feature_modified.idx].append(attr_modifier.value_modifier)

        for key, values in values_change.items():
            if key in result_values_dict:
                values = sorted(values)
                rounded_value = 0
                for i, value in enumerate(values):
                    if i == 0:
                        result_values_dict[key][0] += value
                    else:
                        rounded_value += value
                is_positive = False
                if rounded_value >= 0:
                    is_positive = True
                rounded_value = math.floor(abs(rounded_value))
                result_values_dict[key][0] += rounded_value if is_positive else -rounded_value

        for feature, attr in result_values_dict.items():
            attr[0] = (
                attr[0].convert_to_lang_and_prettify(language_iso2)
                if hasattr(attr[0], "convert_to_lang_and_prettify")
                else attr[0]
            )
        for f_idx in LIMITED_CUSTOM_FEATURES_IDXS_TO_VIEW:
            if limit_view and f_idx in result_values_dict:
                del result_values_dict[f_idx]
        product_attr_specification = dict(result_values_dict)
        product_attr_specification_sorted = dict(sorted(product_attr_specification.items()))
        return product_attr_specification_sorted

    def get_filtered_attributes(self, sku, attr_idx_list, channel_idx, get_all=False):
        errors = []
        product_custom = self._get_product_custom(sku, channel_idx)
        attr_idx_list = self.unpack_nested_list(attr_idx_list)

        # Wszystkie wymagane featury do customizacji
        customization_memberships = FeatureInFeatureSet.objects.filter(
            feature_set=product_custom.customization_feature_set,
            feature__feature_type__in=[FeatureTypeEnum.SELECT, FeatureTypeEnum.MULTISELECT],
        )
        all_needed_feature_select = list(customization_memberships.values_list("feature__idx", flat=True))

        # Effective flag: the per-set override when set, else Feature.is_required.
        features_required = customization_memberships.effective_required().values_list("feature__idx", flat=True)

        # Wszystkie wybrane featury do customizacji
        chosen_product_attr_queryset = Attribute.objects.filter(
            feature__is_for_customization=True,
            idx__in=attr_idx_list,
            feature__feature_type__in=[FeatureTypeEnum.SELECT, FeatureTypeEnum.MULTISELECT],
            feature__feature_in_feature_set__feature_set=product_custom.customization_feature_set,
        ).select_related("feature", "group")
        affected_values = list(set(attr_idx_list) - set(chosen_product_attr_queryset.values_list("idx", flat=True)))
        if affected_values:
            errors.append(
                ErrorInfo(
                    message="Attributes not found",
                    code="attributes_not_found",
                    affected_values=affected_values,
                    affected_field="idx",
                    extra={},
                )
            )
        # Wszystkie defaultowe featury do customizacji
        default_product_attr_query = (
            ProductAttribute.objects.filter(
                product=product_custom,
                feature__is_for_customization=True,
                feature__feature_type__in=[FeatureTypeEnum.SELECT, FeatureTypeEnum.MULTISELECT],
                feature__feature_in_feature_set__feature_set=product_custom.customization_feature_set,
            )
            .select_related("product", "attribute")
            .values_list("attribute__idx", flat=True)
        )
        default_attr_queryset = Attribute.objects.filter(idx__in=default_product_attr_query).select_related(
            "feature", "group"
        )
        unique_chosen_and_default_combination_attrs = {}

        for attr_chosen in chosen_product_attr_queryset:
            if attr_chosen.feature.idx not in unique_chosen_and_default_combination_attrs:
                unique_chosen_and_default_combination_attrs[attr_chosen.feature.idx] = []

            unique_chosen_and_default_combination_attrs[attr_chosen.feature.idx].append(
                {"idx": attr_chosen.idx, "group__idx": attr_chosen.group.idx if attr_chosen.group else None}
            )

        for attr_default in default_attr_queryset:
            if attr_default.feature.idx not in unique_chosen_and_default_combination_attrs:
                unique_chosen_and_default_combination_attrs[attr_default.feature.idx] = []
                unique_chosen_and_default_combination_attrs[attr_default.feature.idx].append(
                    {"idx": attr_default.idx, "group__idx": attr_default.group.idx if attr_default.group else None}
                )

        for f9e, attr in unique_chosen_and_default_combination_attrs.items():
            if f9e not in all_needed_feature_select and f9e not in unique_chosen_and_default_combination_attrs:
                unique_chosen_and_default_combination_attrs[f9e] = [{"idx": None, "group__idx": None}]

        # pobranie wykluczeń oraz wymuszeń defaultowych wartości
        all_restriction_attr_query, all_default_attr_query, all_coerce_attr_query = self.get_global_restriction_query(
            product_custom
        )
        all_default_attr_query, am_all = self.get_restrictions_query_by_type(
            unique_chosen_and_default_combination_attrs,
            product_custom,
            AttributeModifierTypeEnum.DEFAULT,
            all_default_attr_query,
        )

        default_attr_queryset = (
            Attribute.objects.filter(*all_default_attr_query, _connector=Q.OR) | default_attr_queryset
            if all_default_attr_query
            else default_attr_queryset
        )

        # Priorytet EXCLUDE nad DEFAULT: wykluczamy atrybuty które mają wpis EXCLUDE w AttributeModifier
        if all_restriction_attr_query:
            default_attr_queryset = default_attr_queryset.exclude(*all_restriction_attr_query, _connector=Q.OR)

        for attr_default in default_attr_queryset:
            if attr_default.feature.idx not in unique_chosen_and_default_combination_attrs:
                unique_chosen_and_default_combination_attrs[attr_default.feature.idx] = [
                    {"idx": attr_default.idx, "group__idx": attr_default.group.idx if attr_default.group else None}
                ]
        all_restriction_attr_query, am_value = self.get_restriction_query_filters(
            unique_chosen_and_default_combination_attrs, product_custom, all_restriction_attr_query
        )

        _, coerce_dependent_attr = self.get_restrictions_query_by_type(
            unique_chosen_and_default_combination_attrs,
            product_custom,
            AttributeModifierTypeEnum.COERCE,
            all_coerce_attr_query,
        )

        # Wszystkie atrybuty, które są wybrane, ale mają wykluczenia
        chosen_product_attr_queryset = chosen_product_attr_queryset.exclude(*all_restriction_attr_query).values_list(
            "feature__idx", flat=True
        )
        chosen_feature_idx = list(chosen_product_attr_queryset.values_list("feature__idx", flat=True))

        result_list = {}
        result_list_list = []
        added_feature = []
        all_attr_chosen_default = [
            *chosen_product_attr_queryset.values_list(
                "feature__idx", "idx", "feature__feature_type", "feature__feature_in_feature_set__feature_set__pk"
            ),
            *default_attr_queryset.values_list(
                "feature__idx", "idx", "feature__feature_type", "feature__feature_in_feature_set__feature_set__pk"
            ),
        ]

        for f, a, fft, ffff in all_attr_chosen_default:
            if (
                any([f in all_needed_feature_select, fft == FeatureTypeEnum.MULTISELECT])
                and any([f not in added_feature, fft == FeatureTypeEnum.MULTISELECT])
                and ffff == product_custom.customization_feature_set.pk
            ):
                if f in all_needed_feature_select and not get_all:
                    all_needed_feature_select.remove(f)

                if f not in result_list:
                    result_list[f] = []

                result_list_list.append(a)
                result_list[f].append(a)
                added_feature.append(f)

        # Wykluczanie po color hashu
        intersection_query = []
        intersection_attrs_colors_match = {}
        try:
            all_intersetion_attrs_colors_match = AttributeModifier.objects.get_all_intersection_of_two_features(
                unique_chosen_and_default_combination_attrs
            )
            for feature1, feature2, attrs_colors_match in all_intersetion_attrs_colors_match:
                if feature1[0].idx in result_list.keys():
                    intersection_query.append(Q(Q(feature__idx=feature2[0]) & ~Q(idx__in=feature2[1])))
                if feature2[0].idx in result_list.keys():
                    intersection_query.append(Q(Q(feature__idx=feature1[0]) & ~Q(idx__in=feature1[1])))
                for attr_1, attr_2 in attrs_colors_match.items():
                    if attr_1.idx not in intersection_attrs_colors_match:
                        intersection_attrs_colors_match[attr_1.idx] = []
                    if attr_2.idx not in intersection_attrs_colors_match:
                        intersection_attrs_colors_match[attr_2.idx] = []

                    if attr_2.idx not in intersection_attrs_colors_match[attr_1.idx]:
                        intersection_attrs_colors_match[attr_1.idx].append(attr_2)
                    if attr_1.idx not in intersection_attrs_colors_match[attr_2.idx]:
                        intersection_attrs_colors_match[attr_2.idx].append(attr_1)
        except ValueError:
            pass

        picture_subquery = ProductAttributeImage.objects.filter(
            attribute=OuterRef("pk"), product=None, picture__isnull=False
        ).values("picture__image")[:1]

        color_hash_subquery = ProductAttributeImage.objects.filter(
            attribute=OuterRef("pk"), product=None, color_hash__isnull=False
        ).values("color_hash")[:1]

        all_product_attr_objs = (
            Attribute.objects.filter(
                feature__is_for_customization=True,
                feature__feature_type__in=[FeatureTypeEnum.SELECT, FeatureTypeEnum.MULTISELECT],
                feature__feature_in_feature_set__feature_set=product_custom.customization_feature_set,
            )
            .select_related("feature")
            .annotate(
                is_default=models.Case(
                    models.When(idx__in=default_attr_queryset.values_list("idx", flat=True), then=True), default=False
                ),
                picture=Subquery(picture_subquery),
                color_hash=Subquery(color_hash_subquery),
            )
        )

        # wyklucz z głownego query attrybuty które są wymuszone
        all_product_attr_objs_ex1 = all_product_attr_objs.exclude(*all_restriction_attr_query, _connector=Q.OR)
        # wyklucz z głownego query attrybuty część wspólna
        all_product_attr_objs_ex2 = all_product_attr_objs_ex1.exclude(*intersection_query, _connector=Q.OR)
        excluded_attrs = all_product_attr_objs.exclude(pk__in=all_product_attr_objs_ex2.values_list("pk", flat=True))
        # dodaj do query inforamcję które color hashe w ramach jakiego feature są wykluczone
        all_product_attr_objs_ex2 = all_product_attr_objs_ex1.annotate(
            feature__excluded_color_hash=Subquery(
                excluded_attrs.filter(feature=OuterRef("feature"), color_hash__isnull=False)
                .values("feature")
                .annotate(color_hash_list=ArrayAgg(F("color_hash"), distinct=True))
                .values("color_hash_list")[:1]
            )
        )

        attrs_to_delete_from_query = {}
        features_to_delete_from_query = []

        # Wyświetl komunikat o konieczności usunięcia atrybutu, jeżeli użytkownik go wybrał a jest wykluczony
        for attr_ch in chosen_product_attr_queryset:
            for attr_ex in excluded_attrs:
                if attr_ex == attr_ch:
                    if attr_ex.feature.idx not in attrs_to_delete_from_query:
                        attrs_to_delete_from_query[attr_ex.feature.idx] = []

                    if attr_ex.idx not in attrs_to_delete_from_query[attr_ex.feature.idx]:
                        attrs_to_delete_from_query[attr_ex.feature.idx].append(attr_ex.idx)

        if attrs_to_delete_from_query:
            for f, a in attrs_to_delete_from_query.items():
                features_to_delete_from_query.append(a)
                errors.append(
                    ErrorInfo(
                        message="Attributes excluded. Changed to default.",
                        code="attributes_excluded",
                        affected_field=f,
                        affected_values=a,
                        extra={},
                    )
                )

        grouped_coerce_dependent_attr = {}
        for feature, attr, attrs_to_coerce in coerce_dependent_attr:
            key = feature
            if key not in grouped_coerce_dependent_attr:
                grouped_coerce_dependent_attr[key] = []
            grouped_coerce_dependent_attr[key].append(attrs_to_coerce)

        for f, a in grouped_coerce_dependent_attr.items():
            errors.append(
                ErrorInfo(
                    message="Attribute are coerced. Need to change.",
                    code="attributes_coerced",
                    affected_field=f,
                    affected_values=a,
                    extra={},
                )
            )
        errors_added = []
        for f, a in result_list.items():
            for attr in a:
                intersection_feature_group = {}

                intersection_attr = intersection_attrs_colors_match.get(attr, None)

                if not intersection_attr:
                    continue

                for attr in intersection_attr:
                    if attr.idx in excluded_attrs.values_list("idx", flat=True):
                        continue

                    if attr.feature.idx not in intersection_feature_group:
                        intersection_feature_group[attr.feature.idx] = []

                    if attr.idx not in intersection_feature_group[attr.feature.idx]:
                        intersection_feature_group[attr.feature.idx].append(attr.idx)

                for in_f, in_a in intersection_feature_group.items():
                    in_a = list(set(in_a) - set(errors_added))
                    add_error = True
                    for attr in in_a:
                        for attr_requested in all_attr_chosen_default:
                            if attr_requested[1] == attr and attr in attr_idx_list:
                                add_error = False
                                break
                    if add_error:
                        errors.append(
                            ErrorInfo(
                                message="Attributes need to be changed.",
                                code="attributes_need_to_be_changed",
                                affected_field=in_f,
                                affected_values=in_a,
                                extra={},
                            )
                        )
                        errors_added.extend(in_a) if in_a else None

        # Usuń wykluczonych atrybutów z result_list_list (EXCLUDE ma priorytet nad DEFAULT)
        excluded_attr_idx_list = list(excluded_attrs.values_list("idx", flat=True))
        result_list_list = [idx for idx in result_list_list if idx not in excluded_attr_idx_list]

        am_value_filtered = []
        for modifier in am_value:
            modifier_attrs = list(modifier.attributes.all().values_list("idx", flat=True))
            if not any(attr_idx in excluded_attr_idx_list for attr_idx in modifier_attrs):
                am_value_filtered.append(modifier)

        features_with_available_attrs = set(
            all_product_attr_objs.exclude(idx__in=excluded_attr_idx_list).values_list("feature__idx", flat=True)
        )
        features_final = Attribute.objects.filter(idx__in=result_list_list).values_list("feature__idx", flat=True)
        for f_req in features_required:
            if f_req not in features_final and f_req in features_with_available_attrs:
                errors.append(
                    ErrorInfo(
                        message="Required features are missing.",
                        code="required_features_missing",
                        affected_values=[f_req],
                        affected_field="feature__idx",
                        extra={},
                    )
                )

        return (all_needed_feature_select, errors, all_product_attr_objs_ex2, result_list_list, am_value_filtered)

    # django-checkout
    # django-matrix
    def get_custom_attributes_idx(self, product, attr_idx_list, channel_idx=None, limit_view=False):
        (all_needed_feature_select, errors, all_product_attr_objs, result_list, am_value) = (
            self.get_filtered_attributes(product, attr_idx_list, channel_idx)
        )

        attributes_query = all_product_attr_objs.filter(idx__in=result_list)
        if limit_view:
            attributes_query = attributes_query.exclude(feature__idx__in=LIMITED_CUSTOM_FEATURES_IDXS_TO_VIEW)
        return attributes_query, am_value, errors

    # django-matrix
    def get_all_available_attributes(self, product, attr_idx_list, channel_idx=None):
        (all_needed_feature_select, errors, all_product_attr_objs, result_list, am_value) = (
            self.get_filtered_attributes(product, attr_idx_list, channel_idx, get_all=True)
        )
        all_product_attr_objs = all_product_attr_objs.filter(feature__idx__in=all_needed_feature_select)

        return all_product_attr_objs, errors

    def get_all_details_attributes_values(self, product_custom_sku, all_attr_modifier, channel_idx, language_iso2):
        product_attr_specification_sorted = self.get_custom_attributes_details(
            product_custom_sku, all_attr_modifier, channel_idx, language_iso2
        )
        return product_attr_specification_sorted


class ProductAttribute(models.Model):
    product = models.ForeignKey(
        "Product",
        related_name="products_attributes",
        verbose_name="product",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )

    feature: "Feature" = models.ForeignKey(
        "Feature",
        related_name="products_attributes",
        verbose_name="feature",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )

    attribute = models.ForeignKey(
        "Attribute",
        related_name="products_attributes",
        verbose_name="attribute",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    value_bool = models.BooleanField(blank=True, null=True)
    value_decimal = models.DecimalField(blank=True, null=True, max_digits=24, decimal_places=6)
    value_datetime = models.DateTimeField(blank=True, null=True)
    overridden_langs = models.JSONField(default=list, blank=True)
    value_txt = models.TextField(null=True, blank=True)
    value_txt_t9n = models.JSONField(null=True, blank=True)  # { 'pl': "...", 'en': "...", ... }
    value_json = models.JSONField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = ProductAttributeManager()

    def get_value(self, lang=None, langs=None):
        feature_type = self.feature.feature_type
        if feature_type == FeatureTypeEnum.BOOL:
            return self.value_bool
        if feature_type == FeatureTypeEnum.DECIMAL:
            return self.value_decimal
        if feature_type == FeatureTypeEnum.JSON:
            return self.value_json
        if feature_type in (FeatureTypeEnum.VARCHAR255, FeatureTypeEnum.TEXT):
            return self.value_txt
        if feature_type == FeatureTypeEnum.SELECT:
            if self.attribute is None:
                return None
            return self.attribute.name
        if feature_type == FeatureTypeEnum.MULTISELECT:
            if self.attribute is None:
                return None
            return self.attribute.name
        if feature_type == FeatureTypeEnum.DATETIME:
            return self.value_datetime
        if feature_type in (FeatureTypeEnum.VARCHAR255_T9N, FeatureTypeEnum.TEXT_T9N):
            if self.value_txt_t9n is None:
                return ""
            if not isinstance(self.value_txt_t9n, dict):
                return ""
            if lang is not None and lang in self.value_txt_t9n:
                value = self.value_txt_t9n[lang]
                if value is not None:
                    value = str(value)
                    value = value.strip()
                    if len(value) > 0:
                        return value
            default_langs = set(
                [self.product.shop.default_language.iso2, settings.T9N_DEFAULT_LANG]
                + [*self.value_txt_t9n.keys()]  # lista kluczy dict
            )
            for lang in default_langs:
                if lang in self.value_txt_t9n:
                    value = self.value_txt_t9n[lang]
                    if value is not None:
                        value = str(value)
                        value = value.strip()
                        if len(value) > 0:
                            return value
            return ""
        if feature_type == FeatureTypeEnum.JSON_T9N:
            if self.value_json is None:
                return None
            if not isinstance(self.value_json, dict):
                return None
            if lang is not None and lang in self.value_json:
                return self.value_json[lang]

            default_langs = set(
                [self.product.shop.default_language.iso2, settings.T9N_DEFAULT_LANG]
                + [*self.value_json.keys()]  # lista kluczy dict
            )
            for lang in default_langs:
                if lang in self.value_json:
                    value = self.value_json[lang]
                    if value is not None:
                        return value
            return None
        if feature_type in [FeatureTypeEnum.TEMPERATURE, FeatureTypeEnum.MASS, FeatureTypeEnum.LENGTH]:
            default_unit, model_unit = self.feature.get_cls_unit_conversion()

            if default_unit and model_unit and self.value_decimal is not None:
                if lang:
                    return model_unit(self.value_decimal, default_unit)
                elif langs:
                    return {
                        lang: model_unit(self.value_decimal, default_unit).convert_to_lang_and_prettify(lang)
                        for lang in langs
                    }
            else:
                return self.value_decimal

        raise Exception(f"Can not get_value() of feature_type={feature_type}")

    def validate_values(self):
        feature_type = self.feature.feature_type
        if feature_type == FeatureTypeEnum.BOOL:
            if self.value_bool is None:
                raise ValueError(
                    f"value_bool can not be None for Product sku={self.product.sku} and Feature idx={self.feature.idx}"
                )
            return
        if feature_type == FeatureTypeEnum.DECIMAL:
            if self.value_decimal is None:
                raise ValueError(
                    f"value_decimal can not be None for Product sku={self.product.sku} and Feature idx={self.feature.idx}"
                )
            return
        if feature_type in [FeatureTypeEnum.TEMPERATURE, FeatureTypeEnum.LENGTH, FeatureTypeEnum.MASS]:
            if self.value_decimal is None:
                raise ValueError(
                    f"value_decimal can not be None for Product sku={self.product.sku} and Feature idx={self.feature.idx}"
                )
            return
        if feature_type in [FeatureTypeEnum.VARCHAR255, FeatureTypeEnum.TEXT]:
            if self.value_txt is None:
                raise ValueError(
                    f"value_txt can not be None for Product sku={self.product.sku} and Feature idx={self.feature.idx}"
                )
            return
        if feature_type in [FeatureTypeEnum.VARCHAR255_T9N, FeatureTypeEnum.TEXT_T9N]:
            if self.value_txt_t9n is None:
                raise ValueError(
                    f"value_txt_t9n can not be None for Product sku={self.product.sku} and Feature idx={self.feature.idx}"
                )
            return
        if feature_type == FeatureTypeEnum.JSON:
            if self.value_json is None:
                raise ValueError(
                    f"value_json can not be None for Product sku={self.product.sku} and Feature idx={self.feature.idx}"
                )
            return
        if feature_type in [FeatureTypeEnum.SELECT, FeatureTypeEnum.MULTISELECT]:
            if self.attribute is None:
                raise ValueError(
                    f"attribute can not be None for Product sku={self.product.sku} and Feature idx={self.feature.idx}"
                )
            return
        if feature_type == FeatureTypeEnum.JSON_T9N:
            if self.value_json is None:
                raise ValueError(
                    f"value_json can not be None for Product sku={self.product.sku} and Feature idx={self.feature.idx}"
                )
            return
        if feature_type == FeatureTypeEnum.DATETIME:
            if self.value_datetime is None:
                raise ValueError(
                    f"value_datetime can not be None for Product sku={self.product.sku} and Feature idx={self.feature.idx}"
                )
            return
        raise Exception(f"Unsupported feature_type={feature_type}")

    def validate_feature(self):
        if self.attribute is None:
            return
        if self.feature != self.attribute.feature:
            raise ValueError(
                f"ProductAttribute: attribute={self.attribute.idx} does not belong to feature={self.feature.idx}"
            )
        if self.product.feature_set is None:
            raise ValueError(
                f"ProductAttribute: product sku={self.product.sku} doesnt have FeatureSet so can not have ProductAttributes"
            )
        if (
            self.feature.scope != FeatureScopeEnum.SYSTEM
            and self.feature not in self.product.feature_set.features.all()
        ):
            raise ValueError(
                f"ProductAttribute: Feature={self.feature.idx} does not belong to Product sku={self.product.sku} FeatureSet={self.product.feature_set.idx}"
            )

    @staticmethod
    def get_value_name_by_feature_type(feature_type) -> str:
        match feature_type:
            case FeatureTypeEnum.UNKNOWN:
                return "value_txt"
            case FeatureTypeEnum.BOOL:
                return "value_bool"
            case FeatureTypeEnum.DECIMAL:
                return "value_decimal"
            case FeatureTypeEnum.VARCHAR255:
                return "value_txt"
            case FeatureTypeEnum.VARCHAR255_T9N:
                return "value_txt_t9n"
            case FeatureTypeEnum.TEXT:
                return "value_txt"
            case FeatureTypeEnum.TEXT_T9N:
                return "value_txt_t9n"
            case FeatureTypeEnum.SELECT:
                return "attribute"
            case FeatureTypeEnum.MULTISELECT:
                return "attribute"
            case FeatureTypeEnum.JSON:
                return "value_json"
            case FeatureTypeEnum.JSON_T9N:
                return "value_json"
            case FeatureTypeEnum.DATETIME:
                return "value_datetime"
            case FeatureTypeEnum.TEMPERATURE:
                return "value_decimal"
            case FeatureTypeEnum.LENGTH:
                return "value_decimal"
            case FeatureTypeEnum.MASS:
                return "value_decimal"

    def save(self, *args, **kwargs):
        self.validate_feature()
        self.validate_values()
        super().save(*args, **kwargs)

    def __str__(self):
        return "%s" % (self.id,)

    class Meta:
        ordering = []
        verbose_name_plural = "products attributes"
        constraints = [
            # nulls_distinct=False: a feature-based value (e.g. name) has attribute=NULL.
            # Default Postgres NULL-distinctness lets duplicate (product, feature, NULL)
            # rows slip past the constraint, which crashed the product list via
            # name_lang().get(). Treat NULLs as equal so the DB rejects the duplicate.
            models.UniqueConstraint(
                fields=["product", "feature", "attribute"],
                name="uniq_product_feature_attribute",
                nulls_distinct=False,
            )
        ]
        indexes = [models.Index(fields=["attribute", "product"], name="idx_productattribute_optimized")]

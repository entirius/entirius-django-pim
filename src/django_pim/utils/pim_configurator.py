# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging
import os
import sys

import trafaret as tf
import yaml
from django_regional.models import Currency, Language
from service_management.models import BusinessUnit, Shop

from django_pim.models import (
    Attribute,
    Feature,
    FeatureScopeEnum,
    FeatureSet,
    FeatureType,
    FeatureTypeEnum,
    FilterTypeEnum,
    FrontendInputTypeEnum,
    ProductCategory,
)

logger = logging.getLogger(__name__)

#
# Config file validators
#
tfNameT9n = tf.Dict(
    {
        tf.Key("pl", optional=True): tf.Or(tf.String(), tf.Int()),
        tf.Key("en", optional=True): tf.Or(tf.String(), tf.Int()),
    }
)
tfAttribute = tf.Dict(
    {
        tf.Key("idx"): tf.Or(tf.String(), tf.Int()),
        tf.Key("pl", optional=True): tf.Or(tf.String(), tf.Int()),
        tf.Key("en", optional=True): tf.Or(tf.String(), tf.Int()),
    }
)
tfFeature = tf.Dict(
    {
        tf.Key("idx"): tf.String(),
        tf.Key("name"): tfNameT9n,
        tf.Key("scope", optional=True): tf.String(),
        tf.Key("type"): tf.String(),
        tf.Key("frontend_input_type", optional=True): tf.String(),
        tf.Key("filter_type", optional=True): tf.String(),
        tf.Key("display_order", optional=True): tf.Int(),
        tf.Key("is_comparable"): tf.Bool(),
        tf.Key("is_filterable"): tf.Bool(),
        tf.Key("is_required"): tf.Bool(),
        tf.Key("is_searchable"): tf.Bool(),
        tf.Key("is_visible"): tf.Bool(),
        tf.Key("attributes", optional=True): tf.List(tfAttribute),
    }
)
tfFeatureSet = tf.Dict(
    {tf.Key("idx"): tf.String(), tf.Key("name"): tf.String(), tf.Key("features"): tf.List(tf.String())}
)
tfCategory = tf.Dict(
    {
        tf.Key("idx"): tf.String(),
        tf.Key("name"): tfNameT9n,
        tf.Key("is_active", optional=True): tf.Bool(),
        tf.Key("children", optional=True): tf.List(tf.Any),
        tf.Key("url_key_t9n", optional=True): tfNameT9n,
    }
)
tfShop = tf.Dict(
    {
        tf.Key("idx"): tf.String(),
        tf.Key("name"): tf.String(),
        tf.Key("languages"): tf.List(tf.String(), min_length=1),
        tf.Key("currencies"): tf.List(tf.String(), min_length=1),
        tf.Key("default_language"): tf.String(),
        tf.Key("default_currency"): tf.String(),
        tf.Key("categories", optional=True): tf.List(tfCategory),
    }
)
tfBusinessUnit = tf.Dict(
    {
        tf.Key("idx"): tf.String(),
        tf.Key("name"): tf.String(),
        tf.Key("shops", optional=True): tf.List(tfShop),
        tf.Key("features", optional=True): tf.List(tfFeature),
        tf.Key("features sets", optional=True): tf.Any(),
    }
)
tfConfg = tf.Dict(
    {
        tf.Key("system", optional=True): tf.Dict({tf.Key("features", optional=True): tf.List(tfFeature)}),
        tf.Key("business units", optional=True): tf.List(tfBusinessUnit),
    }
)


class PimConfigurator:
    def __init__(self):
        self.document = None

    def info(self, msg):
        print(msg)
        logger.info(msg)

    def error(self, msg):
        print(f"ERROR: {msg}")
        logger.error(msg)

    def config_export_as_yml(self, file_path):
        raise Exception("TODO config_export_as_yml")

    def get_feature_type(self, type_idx):
        m = {
            "text": FeatureTypeEnum.TEXT,
            "text_t9n": FeatureTypeEnum.TEXT_T9N,
            "varchar": FeatureTypeEnum.VARCHAR255,
            "varchar_t9n": FeatureTypeEnum.VARCHAR255_T9N,
            "multiselect": FeatureTypeEnum.MULTISELECT,
            "select": FeatureTypeEnum.SELECT,
            "bool": FeatureTypeEnum.BOOL,
            "decimal": FeatureTypeEnum.DECIMAL,
            "datetime": FeatureTypeEnum.DATETIME,
            "temperature": FeatureTypeEnum.TEMPERATURE,
            "length": FeatureTypeEnum.LENGTH,
            "mass": FeatureTypeEnum.MASS,
            "json": FeatureTypeEnum.JSON,
        }
        if type_idx in m:
            return m[type_idx]
        raise Exception(f"Feature type={type_idx} is not supported")

    def get_frontend_input_type(self, feature_type, d_frontend_input_type=None):
        if d_frontend_input_type is None:
            return FrontendInputTypeEnum.DEFAULT
        if feature_type in [FeatureTypeEnum.SELECT, FeatureTypeEnum.MULTISELECT]:
            if d_frontend_input_type == "select_swatch_visual":
                return FrontendInputTypeEnum.SELECT_SWATCH_VISUAL
            if d_frontend_input_type == "select_swatch_text":
                return FrontendInputTypeEnum.SELECT_SWATCH_TEXT
            if d_frontend_input_type == "dropdown":
                return FrontendInputTypeEnum.DROPDOWN
            if d_frontend_input_type == "dropdown_with_price":
                return FrontendInputTypeEnum.DROPDOWN_WITH_PRICE
            if d_frontend_input_type == "pallete_color":
                return FrontendInputTypeEnum.PALETTE_COLOR
        return FrontendInputTypeEnum.DEFAULT

    def get_filter_type(self, feature_type, d_filter_type=None):
        if d_filter_type is None:
            return FilterTypeEnum.DEFAULT
        if feature_type in [FeatureTypeEnum.SELECT, FeatureTypeEnum.MULTISELECT]:
            if d_filter_type == "select_swatch_image":
                return FilterTypeEnum.SELECT_SWATCH_IMAGE
            if d_filter_type == "select_swatch_text":
                return FilterTypeEnum.SELECT_SWATCH_TEXT
            if d_filter_type == "slide":
                return FilterTypeEnum.SLIDE
        return FilterTypeEnum.DEFAULT

    def get_scope(self, scope_idx):
        m = {"system": FeatureScopeEnum.SYSTEM, "global": FeatureScopeEnum.GLOBAL}
        if scope_idx in m:
            return m[scope_idx]
        raise Exception(f"Feature scope={scope_idx} is not supported")

    def import_feature(self, scope, business_unit, d_feature, display_order=None):
        feature_type = self.get_feature_type(d_feature["type"])
        feature_idx = str(d_feature["idx"])
        display_order = d_feature["display_order"] if "display_order" in d_feature else display_order
        try:
            feature = Feature.objects.get(idx=feature_idx, business_unit=business_unit)
            if feature.feature_type != feature_type:
                self.info(
                    f'Feature "{feature_idx}" type is changed: "{FeatureType.labelFromId(feature.feature_type)}" => "{FeatureType.labelFromId(feature_type)}", removing all related ProductsAttributes'
                )
                feature.products_attributes.all().delete()
        except Feature.DoesNotExist:
            pass
        frontend_input_type = self.get_frontend_input_type(feature_type, d_feature.get("frontend_input_type", None))
        filter_type = self.get_filter_type(feature_type, d_feature.get("filter_type", None))

        feature, created = Feature.objects.update_or_create(
            idx=feature_idx,
            business_unit=business_unit,
            defaults={
                "feature_type": feature_type,
                "frontend_input_type": frontend_input_type,
                "filter_type": filter_type,
                "scope": scope,
                "display_order": display_order,
                "name_t9n": d_feature["name"],
                "is_required": d_feature["is_required"],
                "is_visible": d_feature["is_visible"],
                "is_filterable": d_feature["is_filterable"],
                "is_searchable": d_feature["is_searchable"],
                "is_comparable": d_feature["is_comparable"],
            },
        )
        if feature_type in [FeatureTypeEnum.SELECT, FeatureTypeEnum.MULTISELECT]:
            if "attributes" not in d_feature:
                return
            display_order = 0
            for d_attribute in d_feature["attributes"]:
                display_order += 1
                attribute_idx = str(d_attribute["idx"])
                name_t9n = {}
                for lang in d_feature["name"].keys():
                    if lang in d_attribute:
                        name_t9n[lang] = str(d_attribute[lang])
                        attribute, created = Attribute.objects.update_or_create(
                            feature=feature,
                            idx=attribute_idx,
                            defaults={"name_t9n": name_t9n, "display_order": display_order},
                        )

    def import_system_features(self):
        if "system" not in self.document:
            return
        if "features" not in self.document["system"]:
            return
        for d_feature in self.document["system"]["features"]:
            scope = self.get_scope(d_feature["scope"])
            if scope not in [FeatureScopeEnum.SYSTEM, FeatureScopeEnum.GLOBAL]:
                raise Exception("Feature must be in scope system or global, not scope={}".format(d_feature["scope"]))
            self.import_feature(scope=scope, business_unit=None, d_feature=d_feature)

    def import_categories_tree(self, shop, d_categories, parent=None):
        try:
            tf.List(tfCategory).check(d_categories)
        except tf.DataError as e:
            self.error(f"Invalid category data: {e.as_dict()}")
            return
        position = 0
        for d_category in d_categories:
            position += 1
            product_category, created = ProductCategory.objects.update_or_create(
                shop=shop,
                parent_category=parent,
                idx=str(d_category["idx"]),
                defaults={
                    "name_t9n": d_category["name"],
                    "url_key_t9n": d_category.get("url_key_t9n", {}),
                    "position": position,
                    "is_active": d_category["is_active"],
                },
            )
            if "children" in d_category:
                self.import_categories_tree(shop, d_category["children"], parent=product_category)

    def import_bu_shops(self, business_unit, d_bu):
        if "shops" not in d_bu:
            return
        for d_shop in d_bu["shops"]:
            default_language = Language.objects.get(iso2=d_shop["default_language"].lower())
            default_currency = Currency.objects.get(iso3=d_shop["default_currency"].upper())
            shop, created = Shop.objects.update_or_create(
                idx=d_shop["idx"],
                defaults={
                    "business_unit": business_unit,
                    "name": d_shop["name"],
                    "default_language": default_language,
                    "default_currency": default_currency,
                },
            )
            if len(d_shop["languages"]) == 0:
                self.error("Shop idx={} is missing languages".format(d_shop["idx"]))
            for lang_iso2 in d_shop["languages"]:
                lang = Language.objects.get(iso2=lang_iso2.lower())
                shop.languages.add(lang)
            if len(d_shop["currencies"]) == 0:
                self.error("Shop idx={} is missing currencies".format(d_shop["idx"]))
            for currency_iso3 in d_shop["currencies"]:
                currency = Currency.objects.get(iso3=currency_iso3.upper())
                shop.currencies.add(currency)
            if "categories" in d_shop:
                self.import_categories_tree(shop, d_shop["categories"])

    def import_bu_features(self, business_unit, d_bu):
        if "features" not in d_bu:
            return
        display_order = 100  # 0 .. 100 przeznaczone dla systemowych
        for d_feature in d_bu["features"]:
            display_order += 1
            self.import_feature(
                scope=FeatureScopeEnum.BUSINESS_UNIT,
                business_unit=business_unit,
                d_feature=d_feature,
                display_order=display_order,
            )

    def import_bu_features_sets(self, business_unit, d_bu):
        if "features sets" not in d_bu:
            return
        for d_feature_set in d_bu["features sets"]:
            feature_set, created = FeatureSet.objects.update_or_create(
                idx=d_feature_set["idx"], business_unit=business_unit, defaults={"name": d_feature_set["name"]}
            )
            # joining system features to feature_set
            for feature in Feature.objects.get_system_features():
                feature_set.features.add(feature)
            if "features" in d_feature_set:
                for feature_idx in d_feature_set["features"]:
                    feature = Feature.objects.get_scoped_feature(feature_idx=feature_idx, business_unit=business_unit)
                    feature_set.features.add(feature)

    def import_business_units(self):
        if "business units" not in self.document:
            return
        for d_bu in self.document["business units"]:
            business_unit, created = BusinessUnit.objects.update_or_create(
                idx=d_bu["idx"], defaults={"name": d_bu["name"]}
            )
            self.import_bu_shops(business_unit, d_bu)
            self.import_bu_features(business_unit, d_bu)
            self.import_bu_features_sets(business_unit, d_bu)

    def config_import_from_file(self, file_path):
        if not os.path.isfile(file_path):
            raise Exception("File does not exist: %s" % file_path)
        self.file_path = file_path

        if not file_path.endswith(".yml"):
            self.stdout.write(self.style.ERROR("File with path: {} is not a yml file").format(file_path))
            sys.exit(0)

        logger.info(f'Opening yml file: "{self.file_path}"')
        with open(file_path) as file:
            document = yaml.full_load(file)

        try:
            tfConfg.check(document)
        except tf.DataError as e:
            self.error(e.as_dict())
            # print(e.to_struct())
            raise e
        self.document = document
        logger.info("File is valid yml")

        self.import_system_features()
        self.import_business_units()
        return True

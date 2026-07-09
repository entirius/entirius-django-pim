# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from slugify import slugify

from ..models import Feature, FeatureTypeEnum, FilterTypeEnum, FrontendInputTypeEnum
from ..utils.t9n import t9n_update

logger = logging.getLogger(__name__)


class FeatureManager:
    _cache_features = {}

    def generate_idx(name):
        name = name.strip()
        name = name.lower()
        idx = slugify(name, separator="_")
        Feature.validate_idx(idx)
        return idx

    def get_feature(idx):
        raise Exception("get_feature jest deprecated, ficzery teraz zaleza od Business Unit!")
        if idx in FeatureManager._cache_features:
            return FeatureManager._cache_features[idx]
        feature = Feature.objects.get(idx=idx)
        FeatureManager._cache_features[idx] = feature
        return feature

    def get_or_create_feature(
        idx,
        name_t9n=None,
        is_required=None,
        is_visible=None,
        is_filterable=None,
        is_searchable=None,
        is_comparable=None,
        feature_type=None,
        frontend_input_type=None,
        feature_set=None,
        filter_type=None,
    ):
        """Deprecated"""
        raise Exception("get_or_create_feature jest deprecated, ficzery teraz zaleza od Business Unit!")
        idx = Feature.validate_idx(idx)
        if idx in FeatureManager._cache_features:
            return FeatureManager._cache_features[idx], False

        feature = Feature.objects.filter(idx=idx).first()
        if feature is None:
            if is_required is None:
                is_required = False
            if is_visible is None:
                is_visible = True
            if is_filterable is None:
                is_filterable = False
            if is_searchable is None:
                is_searchable = True
            if is_comparable is None:
                is_comparable = False
            if feature_type is None:
                feature_type = FeatureTypeEnum.UNKNOWN
            if frontend_input_type is None:
                frontend_input_type = FrontendInputTypeEnum.DEFAULT
            if filter_type is None:
                filter_type = FilterTypeEnum.DEFAULT

            created = True
            feature = Feature(
                idx=idx,
                name_t9n=name_t9n,
                is_required=is_required,
                is_visible=is_visible,
                is_filterable=is_filterable,
                is_searchable=is_searchable,
                is_comparable=is_comparable,
                feature_type=feature_type,
                frontend_input_type=frontend_input_type,
                filter_type=filter_type,
            )
            feature.save()
            if feature_set is not None:
                feature.features_sets.add(feature_set)
            logger.info("New Feature: [%s]", idx)
        else:
            created = False
            FeatureManager.update_feature(
                feature=feature,
                name_t9n=name_t9n,
                is_required=is_required,
                is_visible=is_visible,
                is_filterable=is_filterable,
                is_searchable=is_searchable,
                is_comparable=is_comparable,
                feature_type=feature_type,
                frontend_input_type=frontend_input_type,
                filter_type=filter_type,
            )
        FeatureManager._cache_features[idx] = feature
        return (feature, created)

    def update_feature(
        feature,
        name_t9n=None,
        is_required=None,
        is_visible=None,
        is_filterable=None,
        is_searchable=None,
        is_comparable=None,
        feature_type=None,
        frontend_input_type=None,
        filter_type=None,
    ):
        updated = []
        to_save = False
        if name_t9n is not None:
            is_t9n_updated, changed = t9n_update(feature.name_t9n, name_t9n)
            if is_t9n_updated:
                to_save = True
                updated.append("name_t9n: %s" % changed)
        values = {
            "is_required": is_required,
            "is_visible": is_visible,
            "is_filterable": is_filterable,
            "is_searchable": is_searchable,
            "is_comparable": is_comparable,
            "feature_type": feature_type,
            "frontend_input_type": frontend_input_type,
            "filter_type": filter_type,
        }
        for update_field, update_value in values.items():
            current_value = getattr(feature, update_field)
            if update_value is not None and current_value != update_value:
                updated.append(update_field)
                setattr(feature, update_field, update_value)
                to_save = True
        if to_save:
            feature.save()
            logger.info("Feature [%s] updated fields: (%s)", feature.idx, ", ".join(updated))


#   #
#   # automatycznie wykrywa najczesciej uzywane featuresy i wlacza jako filtry
#   #
#   def discover_filters():
#       MIN_PRODUCTS = 30
#       MIN_ATTRIBUTES = 2
#       FILTERS_PER_FEATURE_SET = 10

#       feature_sets = FeatureSet.objects.all()
#       cnt = 0
#       for feature_set in feature_sets:
#           cnt+= 1
#           print('========================================')
#           print('FeatureSet: %s' % feature_set.idx)
#           features_to_sets = FeatureToSet.objects.filter(
#               feature_set = feature_set
#           )
#           features_to_sets = features_to_sets.annotate(
#               num_products = Count('products_attributes'),
#               #num_products = Count('products_attributes'),
#           ).filter(
#               num_products__gte = MIN_PRODUCTS
#           ).order_by(
#               '-num_products'
#           )

#           for feature_to_set in features_to_sets[:FILTERS_PER_FEATURE_SET]:
#               print('Feature: %s %s' % (feature_to_set.feature.idx, feature_to_set.num_products))
#               feature_to_set.is_filter = True
#               feature_to_set.save()

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import logging

from ..models import FeatureTypeEnum, ProductAttribute

logger = logging.getLogger(__name__)


class ProductAttributeManager:
    def get_product_attribute(product, feature, attribute=None):
        query = ProductAttribute.objects.filter(product=product, feature=feature)
        if attribute is not None:
            query = query.filter(attribute=attribute)
            return query.first()
        if feature.feature_type in [FeatureTypeEnum.MULTISELECT]:
            # jesli jest to multiselect, to zwraca liste
            return query
        # moze istniec tylko jeden taki wpis
        return query.first()

    def update_product_attribute(
        product_attribute, attribute=None, value_bool=None, value_decimal=None, value_txt_t9n=None
    ):
        updated = []
        to_save = False
        values = {"value_bool": value_bool, "value_decimal": value_decimal, "value_txt_t9n": value_txt_t9n}
        for update_field, update_value in values.items():
            if update_value is None:
                continue
            current_value = getattr(product_attribute, update_field)
            if current_value != update_value:
                updated.append(update_field)
                setattr(product_attribute, update_field, update_value)
                to_save = True
        if len(updated) > 0:
            if attribute is not None:
                raise ValueError("If value_bool, value_decimal, value_txt_t9n is not None, attribute must be None")
            if product_attribute.attribute is not None:
                product_attribute.attribute = None
                updated.append("attribute=None")
                to_save = True
        else:
            if attribute is not None and product_attribute.attribute != attribute:
                updated.append(
                    'attribute [%s] "%s" => [%s] "%s"'
                    % (product_attribute.id, product_attribute.attribute.idx, attribute.id, attribute.idx)
                )
                product_attribute.attribute = attribute
                to_save = True

        if to_save:
            product_attribute.save()
            logger.info(
                'ProductAttribute [%s] feature="%s" updated fields: (%s)',
                product_attribute.id,
                product_attribute.feature.idx,
                ", ".join(updated),
            )

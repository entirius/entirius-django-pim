# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from itertools import groupby, permutations

from django.db.models import Q

from ..models import ProductLink, ProductLinkToFeature, ProductLinkType


class PimProductLinker:
    def __init__(self):
        super().__init__()

    def link_by_feature(self, products, group_by_feature, link_feature, clear_existing=False):
        def clear(link_type):
            to_delete = ProductLink.objects.filter(link_type=link_type)
            to_delete.delete()

        def get_existing(products, link_type, link_feature=None):
            pks = products.values_list("pk", flat=True)
            existing_q = Q(product__pk__in=pks) or Q(linked_product__pk__in=pks)
            existing = ProductLink.objects.filter(existing_q).filter(link_type=link_type)
            if link_feature is not None:
                existing = existing.filter(productlinktofeature__feature=link_feature)

            return existing

        def key_from_feature(feature):
            def key(product):
                result = product.products_attributes.filter(feature=feature).first()
                if result is None:
                    return -1
                else:
                    return result.attribute.pk

            return key

        link_type = ProductLinkType.objects.get(idx="navigation")

        if clear_existing:
            clear(link_type)

        existing = get_existing(products, link_type, link_feature).values_list("product__pk", "linked_product__pk")
        key = key_from_feature(group_by_feature)
        grouped_by = groupby(sorted(products, key=key), key)
        pairs = (permutations(group, 2) for key, group in grouped_by if key != -1)
        links = [
            ProductLink(product=fst, linked_product=snd, link_type=link_type)
            for pair in pairs
            for fst, snd in pair
            if (fst.pk, snd.pk) not in existing
        ]
        links_with_features = [ProductLinkToFeature(link=link, feature=link_feature) for link in links]

        ProductLink.objects.bulk_create(links)
        ProductLinkToFeature.objects.bulk_create(links_with_features)

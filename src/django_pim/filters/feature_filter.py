# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import django_filters

from django_pim.models import Product, ProductCategory


class FeatureFilter(django_filters.FilterSet):
    category = django_filters.Filter(method="filter_by_category", distinct=True)
    category_url_key = django_filters.Filter(method="filter_by_category_url_key", distinct=True)
    is_filterable = django_filters.Filter(method="filter_by_01")
    is_searchable = django_filters.Filter(method="filter_by_01")
    is_comparable = django_filters.Filter(method="filter_by_01")

    def filter_by_01(self, queryset, name, value):
        try:
            pred_value = bool(int(value))
        except Exception:
            pred_value = False
        predicate = {name: pred_value}
        return queryset.filter(**predicate)

    def filter_by_category(self, queryset, name, value):
        """
        takes http parameter describing category__idx.
        returns queryset of Feature objects that matched with the category.
        """
        category_idx = value
        category_subquery = ProductCategory.objects.filter(idx=category_idx, shop=self.request.channel)
        products_subquery = Product.objects.filter(categories__in=category_subquery).catalog_filterable()
        result = queryset.filter(products_attributes__product__in=products_subquery).distinct()
        return result

    def filter_by_category_url_key(self, queryset, name, value):
        """
        takes http parameter describing category__idx.
        returns queryset of Feature objects that matched with the category.
        """
        lang = self.request.channel.resolve_language(self.request.GET)
        category_url_key = value
        category_subquery = ProductCategory.objects.filter(
            **{f"url_key_t9n__{lang}": category_url_key, "shop": self.request.channel}
        )
        products_subquery = Product.objects.filter(categories__in=category_subquery).catalog_filterable()
        result = queryset.filter(products_attributes__product__in=products_subquery).distinct()

        return result

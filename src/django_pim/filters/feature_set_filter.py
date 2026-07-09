# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db.models import Exists, OuterRef
from django_filters import CharFilter, FilterSet

from django_pim.models import FeatureSet, Product, ProductCategory


class FeatureSetFilter(FilterSet):
    category = CharFilter(method="filter_by_category")
    category_url_key = CharFilter(method="filter_by_category_url_key")

    class Meta:
        model = FeatureSet
        fields = []

    def filter_by_category(self, queryset, name, value):
        """
        takes http parameter describing category__idx.
        returns queryset of FeatureSet objects that matched with the category.
        """
        category_idx = value
        category_subquery = ProductCategory.objects.filter(idx=category_idx, shop=self.request.channel)
        products_subquery = Product.objects.filter(
            categories__in=category_subquery, feature_set__pk=OuterRef("pk")
        ).catalog_filterable()
        result = queryset.filter(Exists(products_subquery))
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
        products_subquery = Product.objects.filter(
            categories__in=category_subquery, feature_set__pk=OuterRef("pk")
        ).catalog_filterable()
        result = queryset.filter(Exists(products_subquery))
        return result

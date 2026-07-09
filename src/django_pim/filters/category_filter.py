# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django_filters import CharFilter, Filter, FilterSet

from django_pim.models import ProductCategory


class CategoryFilter(FilterSet):
    parent_category = CharFilter("parent_category__idx")
    parent_category_url_key = Filter(method="filter_by_parent_category_url_key")

    class Meta:
        model = ProductCategory
        fields = {"tree_deep": ["exact", "lt", "gt"]}

    def filter_by_parent_category_url_key(self, queryset, name, value):
        lang = self.request.channel.resolve_language(self.request.GET)
        t9n_query = {f"parent_category__url_key_t9n__{lang}": value}
        return queryset.filter(**t9n_query)

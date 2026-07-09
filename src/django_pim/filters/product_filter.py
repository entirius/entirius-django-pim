# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json

import django_filters
from django.db.models import Case, Exists, OuterRef, Q, QuerySet, Subquery, When
from django_utils.api.exceptions import BadRequest

from django_pim.models import Product, ProductAttribute, ProductPrice


class IdInFilter(django_filters.BaseInFilter, django_filters.CharFilter):
    def filter(self, qs, value):
        if value == []:
            value = [""]
        elif value is not None:
            ordering = Case(*[When(real_product__sku=sku, then=pos) for pos, sku in enumerate(value)])
            qs = qs.order_by(ordering)

        return super().filter(qs, value)


class UrlKeyInFilter(django_filters.BaseInFilter, django_filters.CharFilter):
    def filter(self, qs, value):
        if value == []:
            value = [""]
        elif value is not None:
            ordering = Case(*[When(real_product__sku=sku, then=pos) for pos, sku in enumerate(value)])
            qs = qs.order_by(ordering)

        return super().filter(qs, value)


class ProductOrderingFilter(django_filters.OrderingFilter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra["choices"] += [("price", "Price"), ("-price", "Price (descending)")]

    def filter(self, qs, value):
        # OrderingFilter is CSV-based, so `value` is a list
        if value is not None:
            outer_q = Q(product__pk=OuterRef("pk")) | Q(
                product__configurable_links__product_configurable__product_ptr__pk=OuterRef("pk")
            )
            price_subquery = ProductPrice.objects.filter(outer_q).order_by("price_brutto").values("price_brutto")[:1]
            qs = qs.annotate(sort_price=Subquery(price_subquery))
            if any(v in ["price"] for v in value):
                return qs.order_by("sort_price")
            elif any(v in ["-price"] for v in value):
                return qs.order_by("-sort_price")
            else:
                return super().filter(qs, value)
        else:
            return super().filter(qs, value)


class ProductFilter(django_filters.FilterSet):
    sku__in = IdInFilter(field_name="real_product__sku")
    category = django_filters.CharFilter(field_name="categories__idx")
    category_url_key = django_filters.Filter(method="filter_by_categories_url_key")
    feature_set = django_filters.CharFilter(field_name="feature_set__idx")
    search = django_filters.Filter(method="text_search")
    price__gt = django_filters.Filter(method="filter_by_price")
    price__lt = django_filters.Filter(method="filter_by_price")
    query = django_filters.CharFilter(method="filter_by_attribute_query")
    is_special_offer = django_filters.Filter(method="filter_by_special_offer")

    order_by = ProductOrderingFilter(
        fields=(("db_created", "created"), ("db_modified", "updated"), ("real_product__sku", "sku"))
    )

    class Meta:
        model = Product
        fields = []

    def filter_by_categories_url_key(self, queryset, name, value):
        lang = self.request.channel.resolve_language(self.request.GET)
        t9n_query = {f"categories__url_key_t9n__{lang}": value}
        return queryset.filter(**t9n_query).order_by("product_in_category__position", "-updated_at")

    def filter_by_attribute_query(self, queryset, name, value):
        """
        function takes json as text and turns it into a dict of kwargs
        representig features and their values
        for objects. filter expression.
        returns filtered queryset.
        """
        try:
            attrs = json.loads(value)
        except Exception:
            raise BadRequest("Invalid attribute query")
        query = Q()
        for key, value_list in attrs.items():
            if not isinstance(value_list, list):
                value_list = [str(value_list)]
            subquery = Q()
            for value in value_list:
                """
                This is a fairly complicated query.
                It first contructs two queries.
                simple fetches all products that have attributes directly bound to them.
                configurable fetches all products that have simple products as subproducts.
                both get combined to get all products that have attributes bound to them in any way
                """
                simple = Product.objects.filter(
                    products_attributes__feature__idx=key, products_attributes__attribute__idx=value
                ).values_list("pk", flat=True)
                configurable = Product.objects.filter(
                    productconfigurable__subproduct_links__subproduct__in=simple
                ).values_list("pk", flat=True)
                subquery = subquery | (Q(pk__in=simple) | Q(pk__in=configurable))
            query = query & subquery

        return queryset.filter(query)

    def filter_by_price(self, queryset, name: str, value: str):
        def get_product_prices(currency: str, min_p, max_p) -> QuerySet:
            query = (
                Q(currency__iso3=currency) & Q(price_brutto__gt=min_p) | Q(special_price__gt=min_p)
                if min_p
                else Q() & Q(price_brutto__lt=max_p) | Q(special_price__lt=max_p)
                if max_p
                else Q()
            )
            queryset = ProductPrice.objects.filter(query)
            return queryset

        min_val = value if name.endswith("__gt") else None
        max_val = value if name.endswith("__lt") else None
        currency = self.request.channel.resolve_currency(self.request.GET)
        prices = get_product_prices(currency, min_val, max_val)

        q = Q(product_prices__in=prices) | Q(
            productconfigurable__subproduct_links__subproduct__product_prices__in=prices
        )

        return queryset.filter(q)

    def text_search(self, queryset, name, value):
        if len(value) < 3:
            raise BadRequest(message="Invalid search query")
        lang = self.request.channel.resolve_language(self.request.GET)
        t9n_query = {f"value_txt_t9n__{lang}__icontains": value}
        q = Q(**t9n_query) | Q(value_txt__icontains=value)
        subquery = ProductAttribute.objects.filter(q, product__pk=OuterRef("pk"), feature__is_searchable=True)
        result = queryset.filter(Exists(subquery))
        return result

    def filter_by_special_offer(self, queryset, name, value):
        if bool(int(value)):
            simples_special_offer = Product.objects.exclude(productsimple__product_prices__special_price=None)
            configs_special_offer = queryset.filter(
                productconfigurable__subproduct_links__subproduct__in=simples_special_offer
            )
            q_obj = Q(pk__in=simples_special_offer.values("pk")) | Q(pk__in=configs_special_offer.values("pk"))
            return queryset.filter(q_obj)
        else:
            return queryset

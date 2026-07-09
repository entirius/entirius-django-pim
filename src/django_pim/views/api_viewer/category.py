# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django_utils.api.decorators import api_view, require_http_method
from django_utils.api.exceptions import NotFound
from django_utils.api.filter import filter_qs
from django_utils.api.pagination import paginate_qs
from django_utils.api.responses import PaginatedResponse, Response

from django_pim.filters import CategoryFilter
from django_pim.models import Channel, Product, ProductCategory, ProductVisibility


def category_to_repr(channel: Channel, params: dict, instance: ProductCategory) -> dict:
    lang = channel.resolve_language(params)

    def get_name_tree(instance: ProductCategory) -> str:
        cat = instance
        result = []
        while True:
            result.append(cat.name_t9n.get(lang, ""))
            if cat.parent_category is not None:
                cat = cat.parent_category
            else:
                break
        return " > ".join(reversed(result))

    def get_products_count(instance: ProductCategory) -> int:
        allowed_visibilities = [ProductVisibility.enumClass.CATALOG, ProductVisibility.enumClass.CATALOG_AND_SEARCH]
        queryset = Product.objects.filter(
            categories__idx=instance.idx, is_enabled=True, visibility__in=allowed_visibilities
        )
        return len(queryset)

    return dict(
        idx=instance.idx,
        parent_idx=(instance.parent_category.idx if instance.parent_category is not None else None),
        name=instance.name_t9n.get(lang, ""),
        parent_name=(instance.parent_category.name_t9n.get(lang, "") if instance.parent_category is not None else None),
        name_tree=get_name_tree(instance),
        tree_deep=instance.tree_deep,
        products_count=get_products_count(instance),
    )


@api_view
@require_http_method("GET")
def view_category(request, idx=None, shop_idx=None, *args, **kwargs):
    params = request.GET
    _to_repr = category_to_repr
    try:
        channel = Channel.objects.get(idx=shop_idx)
        request.channel = channel
    except Channel.DoesNotExist:
        raise NotFound(f"Channel {shop_idx} does not exist")

    queryset = ProductCategory.objects.filter(shop=channel).order_by("tree_deep")

    if idx is not None:
        obj = queryset.filter(idx=idx).first()
        if obj is None:
            raise NotFound
        else:
            response_data = _to_repr(channel, params, obj)
            return Response(response_data)
    else:
        filtered, filtered_obj = filter_qs(CategoryFilter, params, queryset)

        inc_children_param = params.get("inc_children", "0")
        inc_children = True if inc_children_param == "1" else False
        if inc_children:
            filtered = filtered.union(
                ProductCategory.objects.filter(is_active=True, parent_category__in=filtered)
            ).order_by("tree_deep")

        pagination, paginated_data = paginate_qs(params, filtered)
        response_data = [_to_repr(channel, params, elem) for elem in paginated_data]
        return PaginatedResponse(pagination, response_data)

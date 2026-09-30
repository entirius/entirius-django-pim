# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from itertools import chain, groupby
from logging import getLogger

from django.db.models import F, Max, Min, Q
from django.db.models.query import QuerySet
from django_utils.api.decorators import api_view, require_http_method
from django_utils.api.exceptions import NotFound
from django_utils.api.filter import filter_qs
from django_utils.api.pagination import paginate_qs
from django_utils.api.responses import PaginatedResponse, Response

from django_pim import settings
from django_pim.filters import ProductFilter
from django_pim.models import (
    Channel,
    FeatureType,
    FilterType,
    FrontendInputType,
    PictureRole,
    Product,
    ProductAttribute,
    ProductClass,
    ProductPicture,
    ProductPrice,
    Thumb,
)
from django_pim.models.product import ProductVisibility
from django_pim.views.api_viewer.auth import staff_required

logger = getLogger("django")


def products_to_response(channel: Channel, params: dict, qs: QuerySet) -> list[dict]:
    # Make this as fast as possible while still being ok to read
    # Make as few requests to DB as possible
    # Use .values or .values_list where possible

    # language and currency for the whole block
    lang = channel.resolve_language(params)
    currency = channel.resolve_currency(params)

    def fetch_base(ids):
        result = list(
            Product.objects.filter(pk__in=ids).values(
                "pk",
                "db_created",
                "db_modified",
                "is_enabled",
                "visibility",
                "product_class",
                "feature_set__idx",
                ean=F("real_product__ean"),
                sku=F("real_product__sku"),
                quantity=F("productsimple__quantity"),
            )
        )

        # POSTPROCESSING
        for elem in result:
            # Ensure proper datetime formatting
            elem["product_class"] = ProductClass.labelFromId(elem["product_class"])
            elem["visibility"] = ProductVisibility.labelFromId(elem["visibility"])
            elem["feature_set"] = elem.pop("feature_set__idx")
            elem["db_modified"] = elem["db_modified"].strftime("%Y-%m-%d %H:%M:%S")
            elem["db_created"] = elem["db_created"].strftime("%Y-%m-%d %H:%M:%S")
        return result

    def fetch_attributes(ids):
        result = list(
            ProductAttribute.objects.filter(product__pk__in=ids)
            .order_by("product__pk", "feature__display_order")
            .values(
                "product__pk",
                "value_txt",
                f"value_txt_t9n__{lang}",
                "value_bool",
                "value_json",
                "value_decimal",
                value_select=F("attribute__idx"),
                value_select_name=F(f"attribute__name_t9n__{lang}"),
                display_order=F("feature__display_order"),
                feature_idx=F("feature__idx"),
                feature_name=F(f"feature__name_t9n__{lang}"),
                feature_type=F("feature__feature_type"),
                frontend_input_type=F("feature__frontend_input_type"),
                filter_type=F("feature__filter_type"),
            )
        )

        id_to_field = {
            0: "",
            1: "value_bool",
            2: "value_decimal",
            3: "value_txt",
            4: f"value_txt_t9n__{lang}",
            5: "value_txt",
            6: f"value_txt_t9n__{lang}",
            7: "value_select",
            8: "value_select",
            9: "value_json",
        }

        for elem in result:
            value_field = id_to_field[elem["feature_type"]]
            label_field = "value_select_name"
            elem["value"] = elem.get(value_field, None)
            elem["label"] = elem.get(label_field, None)
            elem["feature_type"] = FeatureType.labelFromId(elem["feature_type"])
            elem["frontend_input_type"] = FrontendInputType.labelFromId(elem["frontend_input_type"])
            elem["filter_type"] = FilterType.labelFromId(elem["filter_type"])
            elem.pop("value_bool")
            elem.pop("value_decimal")
            elem.pop("value_select")
            elem.pop("value_select_name")
            elem.pop("value_json")
            elem.pop("value_txt")
            elem.pop(f"value_txt_t9n__{lang}")

        return result

    def fetch_categories(ids):
        result = list(
            Product.objects.filter(pk__in=ids).values(
                "pk",
                tree_deep=F("categories__tree_deep"),
                idx=F("categories__idx"),
                parent_idx=F("categories__parent_category__idx"),
                name=F(f"categories__name_t9n__{lang}"),
                parent_name=F(f"categories__parent_category__name_t9n__{lang}"),
            )
        )
        return result

    def fetch_pictures(ids):
        # Need to do it here, otherwise django will iterate over a queryset
        def make_media_url(media_path: str) -> str | None:
            if media_path is not None:
                return "".join([settings.MEDIA_URL, media_path])
            else:
                return None

        pictures_qs = ProductPicture.objects.filter(product__pk__in=ids)

        pictures = list(
            pictures_qs.values(
                "product__pk",
                "picture_role",
                image=F("picture__image"),
                width=F("picture__width"),
                height=F("picture__height"),
            ).order_by("product__pk", "picture__image")
        )

        thumbs = list(Thumb.objects.filter(image__in=ids).values("image", "width", "height", source=F("image")))

        key_func = lambda x: x["origin__image"]
        grouped = groupby(sorted(thumbs, key=key_func), key=key_func)
        thumbs_by_pic = {}
        for key, group in grouped:
            thumbs_by_pic[key] = list(group)
            for t in thumbs_by_pic[key]:
                t.pop("origin__image")

        # POSTPROCESSING
        for elem in pictures:
            elem["picture_role"] = PictureRole.labelFromId(elem["picture_role"])
            elem["set"] = thumbs_by_pic.get(elem["image"], [])
            elem["set"].append({"source": elem.get("image"), "width": elem.pop("width"), "height": elem.pop("height")})
            for idx, sub_elem in enumerate(elem["set"]):
                elem["set"][idx]["source"] = make_media_url(sub_elem["source"])

        return pictures

    # def fetch_links(ids):

    #     linked = list(
    #         ProductLink.objects.filter(product__pk__in=ids)
    #         .order_by("product__pk")
    #         .values(
    #             "product__pk",
    #             "position",
    #             "link_type",
    #             linked_product_sku=F("linked_product__real_product__sku"),
    #         )
    #     )

    #     for elem in linked:
    #         elem["link_type"] = ProductLinkType.labelFromId(elem["link_type"])

    #     return linked

    def fetch_prices(ids):
        # fetch prices for simple products
        simple_prices = list(
            ProductPrice.objects.filter(product__pk__in=ids)
            .filter(currency__iso3=currency)
            .values(
                "product__pk",
                "currency__iso3",
                "special_price_from",
                "special_price_to",
                special_price_value=F("special_price"),
                price_value=F("price_brutto"),
            )
        )

        # fetch prices for configurable products
        configurable_q = Q(product__configurable_links__product_configurable__product_ptr__pk__in=ids)
        configurable_f = F("product__configurable_links__product_configurable__product_ptr__real_product__sku")
        configurable_prices = list(
            ProductPrice.objects.filter(configurable_q)
            .filter(currency__iso3=currency)
            .values("currency__iso3", sku=configurable_f)
            .order_by("sku")
            .annotate(
                special_price_min=Min("special_price"),
                special_price_max=Max("special_price"),
                price_min=Min("price_brutto"),
                price_max=Max("price_brutto"),
            )
        )

        # POSTPROCESSING
        # merge into a uniform list
        result = []
        for obj in chain(simple_prices, configurable_prices):
            price_min = obj.get("price_min", None), obj.get("special_price_min", None)
            if price_min[0] is None:
                price_min = price_min[1]
            elif price_min[1] is None:
                price_min = price_min[0]
            else:
                price_min = min(price_min)

            price_max = obj.get("price_max", None), obj.get("special_price_min", None)
            if price_max[0] is None:
                price_max = price_max[1]
            elif price_max[1] is None:
                price_max = price_max[0]
            else:
                price_max = max(price_max)

            result.append(
                {
                    "special_price_value": obj.get("sepcial_price_value", None),
                    "special_price_from": obj.get("special_price_from", None),
                    "special_price_to": obj.get("special_price_to", None),
                    "price_value": obj.get("price_value", None),
                    "price_min": price_min,
                    "price_max": price_max,
                    "currency": obj.get("currency__iso3", None),
                    "product__pk": obj["product__pk"],
                }
            )
        return result

    # def fetch_subproducts(ids):
    #     ...

    # Fetching ids in a separate request to avoid nesting selects
    ids = list(qs.values_list("pk", flat=True))
    to_fetch = [
        ("pk", "", fetch_base),
        ("pk", "categories", fetch_categories),
        ("product__pk", "attributes", fetch_attributes),
        ("product__pk", "pictures", fetch_pictures),
        ("product__pk", "prices", fetch_prices),
        # ("product__pk", "links", fetch_links)
    ]

    fields = {}
    for field_to_match, field_name, field_fetcher in to_fetch:
        fields[field_name] = {}
        fetched = field_fetcher(ids)
        key_func = lambda x: x[field_to_match]
        grouped = groupby(sorted(fetched, key=key_func), key=key_func)
        for key, group in grouped:
            fields[field_name][key] = list(group)
            for elem in fields[field_name][key]:
                elem.pop(field_to_match)

    result = []
    for key in ids:
        elem = {}
        for field_name in fields:
            if field_name == "":
                elem.update(fields[field_name][key][0])
            elif key in fields[field_name]:
                elem[field_name] = fields[field_name][key]
            else:
                elem[field_name] = []

        result.append(elem)

    return result


@api_view
@staff_required
@require_http_method("GET")
def view_products(request, sku=None, shop_idx=None, *args, **kwargs):
    to_response = products_to_response
    try:
        channel = Channel.objects.get(idx=shop_idx)
        request.channel = channel
    except Channel.DoesNotExist:
        raise NotFound(f"Channel {shop_idx} does not exist")

    queryset = Product.objects.filter(shop=channel).order_by("real_product__sku")

    if sku is not None:
        queryset = queryset.filter(real_product__sku=sku)
        if len(queryset) != 1:
            raise NotFound
        else:
            response_data = to_response(channel, request.GET, queryset)[0]
            return Response(response_data)
    else:
        filtered_data, filtered_obj = filter_qs(ProductFilter, request.GET, queryset, request)
        pagination, paginated_data = paginate_qs(request.GET, filtered_data)
        response_data = to_response(channel, request.GET, paginated_data)
        return PaginatedResponse(pagination, response_data)

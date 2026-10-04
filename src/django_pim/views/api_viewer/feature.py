# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json
import logging

from django.db.models import Exists, OuterRef, Q
from django.views.decorators.csrf import csrf_exempt
from django_utils.api.decorators import api_view, require_http_method
from django_utils.api.exceptions import BadRequest, NotFound
from django_utils.api.filter import filter_qs
from django_utils.api.pagination import paginate_qs
from django_utils.api.responses import PaginatedResponse, Response

from django_pim.filters import FeatureFilter
from django_pim.models import Attribute, Channel, Feature, FeatureScopeEnum, Product, ProductCategory
from django_pim.views.api_viewer.auth import staff_required

logger = logging.getLogger(__name__)


def feature_to_repr(params: dict, instance: Feature, channel: Channel = None) -> dict:
    lang = channel.resolve_language(params)

    def _get_allowed_values(instance: Feature) -> list:
        """
        If features are filtered by category, allowed values should be too.
        Allowed values are shown only for selects and multiselects.
        """

        category_idx = params.get("category", None)
        if category_idx is not None:
            category_subquery = ProductCategory.objects.filter(idx=category_idx, shop=channel)
            products_subquery = Product.objects.filter(
                categories__in=category_subquery, products_attributes__attribute__pk=OuterRef("pk")
            ).catalog_visible()

            allowed = instance.attributes.filter(Exists(products_subquery)).distinct()
        else:
            allowed = instance.attributes.all().distinct()

        return [dict(idx=obj.idx, name=obj.name_t9n.get(lang, "")) for obj in allowed]

    return dict(
        idx=instance.idx,
        magento_idx=instance.magento_idx,
        name=instance.name_t9n.get(lang, ""),
        scope=instance.scope_name,
        is_required=instance.is_required,
        is_visible=instance.is_visible,
        is_filterable=instance.is_filterable,
        is_searchable=instance.is_searchable,
        is_comparable=instance.is_comparable,
        feature_type=instance.feature_type_name,
        filter_type=instance.filter_type_name,
        frontend_input_type=instance.frontend_input_type_name,
        allowed=_get_allowed_values(instance),
    )


@api_view
@staff_required
@require_http_method("GET")
def view_features(request, idx=None, shop_idx=None, *args, **kwargs):
    _to_repr = feature_to_repr

    try:
        channel = Channel.objects.get(idx=shop_idx)
        request.channel = channel
    except Channel.DoesNotExist:
        raise NotFound(f"Channel {shop_idx} does not exist")

    queryset = Feature.objects.all()

    if idx is not None:
        obj = queryset.filter(idx=idx).first()
        if obj is None:
            raise NotFound
        else:
            response_data = _to_repr(request.GET, obj, channel)
            return Response(response_data)
    else:
        filtered_data, filtered_obj = filter_qs(FeatureFilter, request.GET, queryset, request)

        pagination, paginated_data = paginate_qs(request.GET, filtered_data)
        response_data = [_to_repr(request.GET, elem, channel) for elem in paginated_data]

        return PaginatedResponse(pagination, response_data)


view_features.access_area = "pim.schema"


def get_feature(idx: str) -> Feature | None:
    if idx is None:
        raise Exception()

    try:
        is_system = Q(scope=FeatureScopeEnum.SYSTEM)
        is_global = Q(scope=FeatureScopeEnum.GLOBAL)
        is_business_unit = Q(scope=FeatureScopeEnum.BUSINESS_UNIT)

        result = Feature.objects.filter(is_system | is_global | is_business_unit).filter(is_visible=True).get(idx=idx)
    except Feature.DoesNotExist:
        result = None

    return result


def attribute_to_representation(instance, channel, params):
    lang = channel.resolve_language(params)
    return {"idx": instance.idx, "name": instance.name_t9n.get(lang, ""), "extension": instance.extension}


@api_view
@staff_required
@require_http_method("GET")
def view_feature_attributes(request, shop_idx=None, idx=None, *args, **kwargs):
    try:
        channel = Channel.objects.get(idx=shop_idx)
        request.channel = channel
    except Channel.DoesNotExist:
        raise NotFound(f"Channel {shop_idx} does not exist")

    feature = get_feature(idx)
    if feature is None:
        raise NotFound(f"Feature {idx} does not exist")
    attributes = feature.attributes.order_by("idx").all()
    pagination, paginated_data = paginate_qs(request.GET, attributes)
    response_data = [attribute_to_representation(elem, request.channel, request.GET) for elem in paginated_data]
    return PaginatedResponse(pagination, response_data)


view_feature_attributes.access_area = "pim.schema"


@api_view
@staff_required
@require_http_method("GET")
def view_feature_attribute(request, shop_idx=None, idx=None, attr_idx=None, *args, **kwargs):
    try:
        channel = Channel.objects.get(idx=shop_idx)
        request.channel = channel
    except Channel.DoesNotExist:
        raise NotFound(f"Channel {shop_idx} does not exist")

    feature = get_feature(idx)
    if feature is None:
        raise NotFound(f"Feature {idx} does not exist")
    try:
        attribute = feature.attributes.get(idx=attr_idx)
    except Attribute.DoesNotExist:
        raise NotFound(f"Attribute {idx} does not exist")

    response_data = attribute_to_representation(attribute, request.channel, request.GET)
    return Response(response_data)


view_feature_attribute.access_area = "pim.schema"


@require_http_method("GET")
def view_feature_attribute_extension(request, idx=None, attr_idx=None, *args, **kwargs):
    feature = get_feature(idx)
    if feature is None:
        raise NotFound(f"Feature {idx} does not exist")
    try:
        attribute = feature.attributes.get(idx=attr_idx)
    except Attribute.DoesNotExist:
        raise NotFound(f"Attribute {attr_idx} does not exist")

    response_data = attribute.extension if attribute.extension is not None else {}
    return Response(response_data)


@require_http_method("PUT")
def update_feature_attribute_extension(request, idx=None, attr_idx=None, *args, **kwargs):
    try:
        data = json.loads(request.body)
    except Exception as e:
        raise BadRequest(f"Unable to parse request body as json {e}")

    feature = get_feature(idx)
    if feature is None:
        raise NotFound(f"Feature {idx} does not exist")
    try:
        attribute = feature.attributes.get(idx=attr_idx)
    except Attribute.DoesNotExist:
        raise NotFound(f"Attribute {attr_idx} does not exist")

    attribute.extension = data
    attribute.save()

    response_data = attribute.extension if attribute.extension is not None else {}
    return Response(response_data, "UPDATED")


@csrf_exempt
@api_view
@staff_required
@require_http_method("GET", "PUT")
def view_attribute_extension(request, idx=None, attr_idx=None, *args, **kwargs):
    if request.method == "GET":
        return view_feature_attribute_extension(request, idx, attr_idx, *args, **kwargs)
    else:
        return update_feature_attribute_extension(request, idx, attr_idx, *args, **kwargs)


view_attribute_extension.access_area = "pim.schema"

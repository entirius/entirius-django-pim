# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django_utils.api.decorators import api_view, require_http_method
from django_utils.api.exceptions import NotFound
from django_utils.api.filter import filter_qs
from django_utils.api.pagination import paginate_qs
from django_utils.api.responses import PaginatedResponse, Response

from django_pim.filters import FeatureSetFilter
from django_pim.models import Channel, FeatureSet
from django_pim.views.api_viewer.auth import staff_required
from django_pim.views.api_viewer.feature import feature_to_repr


def feature_set_to_repr(params: dict, instance: FeatureSet, channel: Channel = None) -> dict:
    return dict(
        idx=instance.idx,
        name=instance.name,
        features=[feature_to_repr(params, obj, channel) for obj in instance.features.all()],
    )


@api_view
@staff_required
@require_http_method("GET")
def view_feature_sets(request, idx=None, shop_idx=None, *args, **kwargs):
    _to_repr = feature_set_to_repr

    try:
        channel = Channel.objects.get(idx=shop_idx)
        request.channel = channel
    except Channel.DoesNotExist:
        raise NotFound(f"Channel {shop_idx} does not exist")

    queryset = FeatureSet.objects.all().order_by("idx")

    if idx is not None:
        obj = queryset.filter(idx=idx).first()
        if obj is None:
            raise NotFound
        else:
            response_data = _to_repr(request.GET, obj, channel)
            return Response(response_data)
    else:
        filtered_data, filtered_obj = filter_qs(FeatureSetFilter, request.GET, queryset, request)
        pagination, paginated_data = paginate_qs(request.GET, filtered_data)
        response_data = [_to_repr(request.GET, elem, channel) for elem in paginated_data]
        return PaginatedResponse(pagination, response_data)

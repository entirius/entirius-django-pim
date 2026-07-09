# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Admin API views for channels.

DRF ViewSet for listing available channels (read-only).
"""

from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from ....models import Channel
from ....schemas.responses.channel import ChannelListResponse, ChannelResponse
from ....services import channel_service
from ..errors import internal_error
from ..pagination import AdminPageNumberPagination
from ..permissions import IsAdminUser


def _build_channel_response(channel: Channel) -> ChannelResponse:
    return ChannelResponse(
        pk=channel.pk,
        idx=channel.idx,
        name=channel.name,
        default_language=channel.default_language.iso2 if channel.default_language else "",
        default_currency=channel.default_currency.iso3 if channel.default_currency else "",
        languages=[lang.iso2 for lang in channel.languages.all()],
        is_default=channel.is_default,
        inheritance_enabled=channel.inheritance_enabled,
        default_inheritance_flags=channel.default_inheritance_flags or [],
    )


@extend_schema_view(list=extend_schema(tags=["Channels"]))
class ChannelViewSet(viewsets.ViewSet):
    """Admin endpoints for listing available channels."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="List available channels",
        description="Returns paginated list of all channels (shops).",
        parameters=[
            OpenApiParameter(
                name="search",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Search by channel name",
            ),
            OpenApiParameter(
                name="ordering",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Order by field (e.g. name, -name)",
            ),
            OpenApiParameter(
                name="page", location=OpenApiParameter.QUERY, required=False, type=int, description="Page number"
            ),
            OpenApiParameter(
                name="page_size",
                location=OpenApiParameter.QUERY,
                required=False,
                type=int,
                description="Items per page (max 100)",
            ),
        ],
        responses={200: ChannelListResponse},
    )
    def list(self, request: Request) -> Response:
        try:
            qs = channel_service.list_channels(
                search=request.query_params.get("search"), ordering=request.query_params.get("ordering")
            )

            paginator = AdminPageNumberPagination()
            paginated = paginator.paginate_queryset(qs, request)

            results = [_build_channel_response(ch) for ch in paginated]

            response_data = ChannelListResponse(
                count=qs.count(),
                next=paginator.get_next_link(),
                previous=paginator.get_previous_link(),
                results=results,
            )

            return Response(response_data.model_dump(), status=status.HTTP_200_OK)

        except Exception as e:
            return internal_error(e)

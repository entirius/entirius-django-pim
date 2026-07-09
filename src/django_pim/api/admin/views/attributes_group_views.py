# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Admin API views for attributes groups.

DRF ViewSet for administrative attributes group CRUD operations.
"""

from django.core.exceptions import ObjectDoesNotExist
from django_utils.api.v2_errors import raise_pydantic_as_drf
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from pydantic import ValidationError
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from ....schemas import AttributesGroupListResponse, AttributesGroupResponse
from ....schemas.requests import CreateAttributesGroupRequest, UpdateAttributesGroupRequest
from ....services import (
    create_attributes_group,
    delete_attributes_group,
    get_attributes_group_by_idx,
    list_attributes_groups,
    resolve_attributes_group_name,
    update_attributes_group,
)
from ..errors import internal_error, not_found_response
from ..pagination import AdminPageNumberPagination
from ..permissions import IsAdminUser


@extend_schema_view(
    list=extend_schema(tags=["Attributes Groups"]),
    retrieve=extend_schema(tags=["Attributes Groups"]),
    create=extend_schema(tags=["Attributes Groups"]),
    partial_update=extend_schema(tags=["Attributes Groups"]),
    destroy=extend_schema(tags=["Attributes Groups"]),
)
class AttributesGroupViewSet(viewsets.ViewSet):
    """ViewSet for attributes group management operations."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="List attributes groups",
        description="Get a paginated list of attributes groups with attribute counts",
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=False,
                type=str,
                description="Channel identifier (optional, for validation)",
            ),
            OpenApiParameter(
                name="search",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Search attributes groups by idx or name",
            ),
            OpenApiParameter(
                name="ordering",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Field to order by (e.g., 'idx', '-idx')",
            ),
            OpenApiParameter(
                name="page",
                location=OpenApiParameter.QUERY,
                required=False,
                type=int,
                description="Page number for pagination",
            ),
            OpenApiParameter(
                name="page_size",
                location=OpenApiParameter.QUERY,
                required=False,
                type=int,
                description="Number of items per page (max 100)",
            ),
        ],
        responses={200: AttributesGroupListResponse},
    )
    def list(self, request: Request, channel_idx: str | None = None) -> Response:
        try:
            search = request.query_params.get("search", None)
            ordering = request.query_params.get("ordering")

            groups_qs = list_attributes_groups(
                channel_idx=channel_idx, search=search, ordering=ordering, annotate_counts=True
            )

            paginator = AdminPageNumberPagination()
            paginated_groups = paginator.paginate_queryset(groups_qs, request)

            results = [
                AttributesGroupResponse(
                    pk=group.pk,
                    idx=group.idx,
                    name=resolve_attributes_group_name(group),
                    desc=group.desc,
                    attribute_count=group.attribute_count,
                )
                for group in paginated_groups
            ]

            response_data = AttributesGroupListResponse(
                count=groups_qs.count(),
                next=paginator.get_next_link(),
                previous=paginator.get_previous_link(),
                results=results,
            )

            return Response(response_data.model_dump(), status=status.HTTP_200_OK)

        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Retrieve attributes group by idx",
        description="Get a single attributes group by its unique identifier",
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=False,
                type=str,
                description="Channel identifier (optional, for validation)",
            ),
            OpenApiParameter(
                name="idx", location=OpenApiParameter.PATH, required=True, type=str, description="AttributesGroup idx"
            ),
        ],
        responses={200: AttributesGroupResponse},
    )
    def retrieve(self, request: Request, idx: str, channel_idx: str | None = None) -> Response:
        try:
            group = get_attributes_group_by_idx(idx=idx, channel_idx=channel_idx)
            response_data = AttributesGroupResponse(
                pk=group.pk,
                idx=group.idx,
                name=resolve_attributes_group_name(group),
                desc=group.desc,
                attribute_count=group.attribute_count,
            )
            return Response(response_data.model_dump(), status=status.HTTP_200_OK)

        except ObjectDoesNotExist:
            return not_found_response(f"AttributesGroup with idx '{idx}' not found")
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Create attributes group",
        description="Create a new attributes group for clustering related attribute values",
        request=CreateAttributesGroupRequest,
        responses={201: AttributesGroupResponse},
    )
    def create(self, request: Request) -> Response:
        try:
            data = CreateAttributesGroupRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            group = create_attributes_group(idx=data.idx, name_t9n=data.name_t9n, desc=data.desc)
            response_data = AttributesGroupResponse(
                pk=group.pk,
                idx=group.idx,
                name=resolve_attributes_group_name(group),
                desc=group.desc,
                attribute_count=group.attribute_count,
            )
            return Response(response_data.model_dump(), status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Update attributes group",
        description="Partially update an attributes group by its idx",
        parameters=[
            OpenApiParameter(
                name="idx", location=OpenApiParameter.PATH, required=True, type=str, description="AttributesGroup idx"
            )
        ],
        request=UpdateAttributesGroupRequest,
        responses={200: AttributesGroupResponse},
    )
    def partial_update(self, request: Request, idx: str) -> Response:
        try:
            data = UpdateAttributesGroupRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            fields = {k: v for k, v in data.model_dump().items() if v is not None}
            group = update_attributes_group(idx=idx, **fields)
            response_data = AttributesGroupResponse(
                pk=group.pk,
                idx=group.idx,
                name=resolve_attributes_group_name(group),
                desc=group.desc,
                attribute_count=group.attribute_count,
            )
            return Response(response_data.model_dump(), status=status.HTTP_200_OK)
        except ObjectDoesNotExist:
            return not_found_response(f"AttributesGroup with idx '{idx}' not found")
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Delete attributes group",
        description="Delete an attributes group by its idx",
        parameters=[
            OpenApiParameter(
                name="idx", location=OpenApiParameter.PATH, required=True, type=str, description="AttributesGroup idx"
            )
        ],
        responses={200: {"description": "Deleted counts by model"}},
    )
    def destroy(self, request: Request, idx: str) -> Response:
        try:
            deleted = delete_attributes_group(idx=idx)
            return Response({"deleted": deleted}, status=status.HTTP_200_OK)
        except ObjectDoesNotExist:
            return not_found_response(f"AttributesGroup with idx '{idx}' not found")
        except Exception as e:
            return internal_error(e)

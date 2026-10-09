# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Admin API views for attributes.

DRF ViewSet for administrative attribute CRUD operations.
"""

from django_utils.api.v2_errors import raise_pydantic_as_drf
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from pydantic import ValidationError
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from ....models import Attribute, Feature
from ....schemas import AttributeListResponse, AttributeResponse
from ....schemas.requests import AttributeReorderRequest, CreateAttributeRequest, UpdateAttributeRequest
from ....services import (
    create_attribute,
    delete_attribute,
    get_attribute_by_composite_key,
    list_attributes,
    reorder_attributes,
    resolve_attribute_name,
    update_attribute,
)
from ..errors import internal_error
from ..pagination import AdminPageNumberPagination
from ..permissions import IsAdminUser


@extend_schema_view(
    list=extend_schema(tags=["Attributes"]),
    retrieve=extend_schema(tags=["Attributes"]),
    create=extend_schema(tags=["Attributes"]),
    partial_update=extend_schema(tags=["Attributes"]),
    destroy=extend_schema(tags=["Attributes"]),
)
class AttributeViewSet(viewsets.ViewSet):
    """ViewSet for attribute management with composite key support."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]
    access_area = "pim.schema"

    @extend_schema(
        summary="List attributes",
        description="Get a paginated, filterable list of attributes across all features",
        parameters=[
            OpenApiParameter(
                name="feature_idx",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Filter by parent feature identifier",
            ),
            OpenApiParameter(
                name="group_idx",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Filter by attributes group identifier",
            ),
            OpenApiParameter(
                name="search",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Search attributes by idx or name",
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
        responses={200: AttributeListResponse},
    )
    def list(self, request: Request) -> Response:
        try:
            attributes_qs = list_attributes(
                feature_idx=request.query_params.get("feature_idx"),
                group_idx=request.query_params.get("group_idx"),
                search=request.query_params.get("search"),
            )
            paginator = AdminPageNumberPagination()
            paginated = paginator.paginate_queryset(attributes_qs, request)
            results = [
                AttributeResponse(
                    pk=a.pk,
                    feature_idx=a.feature.idx,
                    idx=a.idx,
                    name=resolve_attribute_name(a),
                    name_t9n=a.name_t9n or {},
                    desc=a.desc,
                    group_idx=a.group.idx if a.group else None,
                    display_order=a.display_order,
                )
                for a in paginated
            ]
            return Response(
                AttributeListResponse(
                    count=attributes_qs.count(),
                    next=paginator.get_next_link(),
                    previous=paginator.get_previous_link(),
                    results=results,
                ).model_dump(),
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Retrieve attribute by composite key",
        description="Get a single attribute identified by its parent feature idx and attribute idx",
        parameters=[
            OpenApiParameter(
                name="feature_idx",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="Parent feature identifier",
            ),
            OpenApiParameter(
                name="idx",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="Attribute identifier within its feature",
            ),
        ],
        responses={200: AttributeResponse},
    )
    def retrieve(self, request: Request, feature_idx: str, idx: str) -> Response:
        try:
            a = get_attribute_by_composite_key(feature_idx, idx)
            return Response(
                AttributeResponse(
                    pk=a.pk,
                    feature_idx=a.feature.idx,
                    idx=a.idx,
                    name=resolve_attribute_name(a),
                    name_t9n=a.name_t9n or {},
                    desc=a.desc,
                    group_idx=a.group.idx if a.group else None,
                    display_order=a.display_order,
                ).model_dump(),
                status=status.HTTP_200_OK,
            )
        except (Attribute.DoesNotExist, Feature.DoesNotExist):
            return Response({"detail": f"Not found: {feature_idx}/{idx}"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Create attribute",
        description="Create a new attribute under the specified feature",
        request=CreateAttributeRequest,
        responses={201: AttributeResponse},
    )
    def create(self, request: Request) -> Response:
        try:
            data = CreateAttributeRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            attr = create_attribute(
                feature_idx=data.feature_idx,
                idx=data.idx,
                name_t9n=data.name_t9n,
                group_idx=data.group_idx,
                display_order=data.display_order,
                desc=data.desc,
            )
            response_data = AttributeResponse(
                pk=attr.pk,
                feature_idx=attr.feature.idx,
                idx=attr.idx,
                name=resolve_attribute_name(attr),
                name_t9n=attr.name_t9n or {},
                desc=attr.desc,
                group_idx=attr.group.idx if attr.group else None,
                display_order=attr.display_order,
            )
            return Response(response_data.model_dump(), status=status.HTTP_201_CREATED)
        except Feature.DoesNotExist:
            return Response({"detail": f"Feature '{data.feature_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Update attribute",
        description="Partially update an attribute identified by composite key (feature_idx + idx)",
        parameters=[
            OpenApiParameter(
                name="feature_idx",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="Parent feature identifier",
            ),
            OpenApiParameter(
                name="idx",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="Attribute identifier within its feature",
            ),
        ],
        request=UpdateAttributeRequest,
        responses={200: AttributeResponse},
    )
    def partial_update(self, request: Request, feature_idx: str, idx: str) -> Response:
        try:
            data = UpdateAttributeRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            fields = {k: v for k, v in data.model_dump().items() if v is not None}
            attr = update_attribute(feature_idx=feature_idx, idx=idx, **fields)
            response_data = AttributeResponse(
                pk=attr.pk,
                feature_idx=attr.feature.idx,
                idx=attr.idx,
                name=resolve_attribute_name(attr),
                name_t9n=attr.name_t9n or {},
                desc=attr.desc,
                group_idx=attr.group.idx if attr.group else None,
                display_order=attr.display_order,
            )
            return Response(response_data.model_dump(), status=status.HTTP_200_OK)
        except (Attribute.DoesNotExist, Feature.DoesNotExist):
            return Response({"detail": f"Attribute '{feature_idx}/{idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Delete attribute",
        description="Delete an attribute identified by composite key (feature_idx + idx)",
        parameters=[
            OpenApiParameter(
                name="feature_idx",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="Parent feature identifier",
            ),
            OpenApiParameter(
                name="idx",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="Attribute identifier within its feature",
            ),
        ],
        responses={200: {"description": "Deleted counts by model"}},
    )
    def destroy(self, request: Request, feature_idx: str, idx: str) -> Response:
        try:
            deleted = delete_attribute(feature_idx=feature_idx, idx=idx)
            return Response({"deleted": deleted}, status=status.HTTP_200_OK)
        except (Attribute.DoesNotExist, Feature.DoesNotExist):
            return Response({"detail": f"Attribute '{feature_idx}/{idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Reorder attributes",
        description="Batch update display_order for multiple attributes",
        tags=["Attributes"],
        request=AttributeReorderRequest,
        responses={200: {"description": "Number of attributes reordered"}, 400: {"description": "Validation error"}},
    )
    def reorder(self, request: Request) -> Response:
        """Batch reorder attributes by updating display_order."""
        try:
            data = AttributeReorderRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            count = reorder_attributes(items=[item.model_dump() for item in data.items])
            return Response({"reordered": count}, status=status.HTTP_200_OK)
        except (Attribute.DoesNotExist, Feature.DoesNotExist):
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

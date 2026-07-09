# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Admin API views for product link types.

DRF ViewSet for administrative link type CRUD operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django_utils.api.v2_errors import raise_pydantic_as_drf
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from pydantic import ValidationError
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

if TYPE_CHECKING:
    from ....models import ProductLinkType
from ....schemas.requests.product_link_type import CreateProductLinkTypeRequest, UpdateProductLinkTypeRequest
from ....schemas.responses.product_link_type import ProductLinkTypeListResponse, ProductLinkTypeResponse
from ....services.product_link_type_service import (
    create_product_link_type,
    delete_product_link_type,
    get_product_link_type_by_idx,
    list_product_link_types,
    resolve_product_link_type_name,
    update_product_link_type,
)
from ..errors import internal_error, not_found_response
from ..pagination import AdminPageNumberPagination
from ..permissions import IsAdminUser


def _build_link_type_response(lt: ProductLinkType) -> ProductLinkTypeResponse:
    return ProductLinkTypeResponse(
        pk=lt.pk,
        idx=lt.idx,
        name_t9n=lt.name_t9n,
        name=resolve_product_link_type_name(lt),
        desc=lt.desc,
        position=lt.position,
        db_created=str(lt.db_created),
    )


@extend_schema_view(
    list=extend_schema(tags=["Link Types"]),
    retrieve=extend_schema(tags=["Link Types"]),
    create=extend_schema(tags=["Link Types"]),
    partial_update=extend_schema(tags=["Link Types"]),
    destroy=extend_schema(tags=["Link Types"]),
)
class ProductLinkTypeViewSet(viewsets.ViewSet):
    """ViewSet for product link type management."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="List link types",
        description="Get a paginated list of product link types",
        parameters=[
            OpenApiParameter(
                name="search",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Search by idx or name",
            ),
            OpenApiParameter(
                name="ordering",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Field to order by",
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
        responses={200: ProductLinkTypeListResponse},
    )
    def list(self, request: Request) -> Response:
        try:
            search = request.query_params.get("search", None)
            ordering = request.query_params.get("ordering")

            qs = list_product_link_types(search=search, ordering=ordering)

            paginator = AdminPageNumberPagination()
            paginated = paginator.paginate_queryset(qs, request)

            results = [_build_link_type_response(lt) for lt in paginated]

            response_data = ProductLinkTypeListResponse(
                count=qs.count(),
                next=paginator.get_next_link(),
                previous=paginator.get_previous_link(),
                results=results,
            )

            return Response(response_data.model_dump(), status=status.HTTP_200_OK)

        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Retrieve link type by idx",
        description="Get a single product link type by its unique identifier",
        parameters=[
            OpenApiParameter(
                name="idx", location=OpenApiParameter.PATH, required=True, type=str, description="Link type idx"
            )
        ],
        responses={200: ProductLinkTypeResponse},
    )
    def retrieve(self, request: Request, idx: str) -> Response:
        try:
            lt = get_product_link_type_by_idx(idx=idx)
            return Response(_build_link_type_response(lt).model_dump(), status=status.HTTP_200_OK)
        except ObjectDoesNotExist:
            return not_found_response(f"ProductLinkType with idx '{idx}' not found")
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Create link type",
        description="Create a new product link type",
        request=CreateProductLinkTypeRequest,
        responses={201: ProductLinkTypeResponse},
    )
    def create(self, request: Request) -> Response:
        try:
            data = CreateProductLinkTypeRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            lt = create_product_link_type(idx=data.idx, name_t9n=data.name_t9n, position=data.position, desc=data.desc)
            return Response(_build_link_type_response(lt).model_dump(), status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Update link type",
        description="Partially update a product link type by its idx",
        parameters=[
            OpenApiParameter(
                name="idx", location=OpenApiParameter.PATH, required=True, type=str, description="Link type idx"
            )
        ],
        request=UpdateProductLinkTypeRequest,
        responses={200: ProductLinkTypeResponse},
    )
    def partial_update(self, request: Request, idx: str) -> Response:
        try:
            data = UpdateProductLinkTypeRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            fields = {k: v for k, v in data.model_dump().items() if v is not None}
            lt = update_product_link_type(idx=idx, **fields)
            return Response(_build_link_type_response(lt).model_dump(), status=status.HTTP_200_OK)
        except ObjectDoesNotExist:
            return not_found_response(f"ProductLinkType with idx '{idx}' not found")
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Delete link type",
        description="Delete a product link type by its idx",
        parameters=[
            OpenApiParameter(
                name="idx", location=OpenApiParameter.PATH, required=True, type=str, description="Link type idx"
            )
        ],
        responses={200: {"description": "Deleted counts by model"}},
    )
    def destroy(self, request: Request, idx: str) -> Response:
        try:
            deleted = delete_product_link_type(idx=idx)
            return Response({"deleted": deleted}, status=status.HTTP_200_OK)
        except ObjectDoesNotExist:
            return not_found_response(f"ProductLinkType with idx '{idx}' not found")
        except Exception as e:
            return internal_error(e)

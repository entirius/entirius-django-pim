# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Admin API views for product links.

DRF ViewSet for managing product-to-product relationships (related, crosssell, etc.).
"""

from django_utils.api.v2_errors import raise_pydantic_as_drf
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from pydantic import ValidationError
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from ....models import Channel, Product, ProductLink, ProductLinkType
from ....schemas.requests.product_link import CreateProductLinkRequest, UpdateProductLinkRequest
from ....schemas.responses.product_link import LinkedProductBriefResponse, ProductLinkListResponse, ProductLinkResponse
from ....services.product_link_service import (
    create_product_link,
    delete_product_link,
    get_product_link,
    list_product_links,
    resolve_product_name,
    update_product_link,
)
from ....services.product_link_type_service import resolve_product_link_type_name
from ..errors import internal_error
from ..pagination import AdminPageNumberPagination
from ..permissions import IsAdminUser


def _build_link_response(link: ProductLink) -> ProductLinkResponse:
    linked = link.linked_product
    return ProductLinkResponse(
        pk=link.pk,
        linked_product=LinkedProductBriefResponse(
            pk=linked.pk, sku=linked.real_product.sku, name=resolve_product_name(linked)
        ),
        link_type_idx=link.link_type.idx if link.link_type else "unknown",
        link_type_name=resolve_product_link_type_name(link.link_type) if link.link_type else "Unknown",
        position=link.position,
        db_created=str(link.db_created),
    )


@extend_schema_view(
    list=extend_schema(tags=["Product Links"]),
    retrieve=extend_schema(tags=["Product Links"]),
    create=extend_schema(tags=["Product Links"]),
    partial_update=extend_schema(tags=["Product Links"]),
    destroy=extend_schema(tags=["Product Links"]),
)
class ProductLinkViewSet(viewsets.ViewSet):
    """ViewSet for product link management."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="List product links",
        description="Get a paginated list of links for a specific product",
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="Channel identifier",
            ),
            OpenApiParameter(
                name="sku", location=OpenApiParameter.PATH, required=True, type=str, description="Product SKU"
            ),
            OpenApiParameter(
                name="link_type",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Filter by link type idx",
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
        responses={200: ProductLinkListResponse},
    )
    def list(self, request: Request, channel_idx: str, sku: str) -> Response:
        try:
            link_type_idx = request.query_params.get("link_type", None)
            ordering = request.query_params.get("ordering")

            qs = list_product_links(channel_idx=channel_idx, sku=sku, link_type_idx=link_type_idx, ordering=ordering)

            paginator = AdminPageNumberPagination()
            paginated = paginator.paginate_queryset(qs, request)

            results = [_build_link_response(link) for link in paginated]

            response_data = ProductLinkListResponse(
                count=qs.count(),
                next=paginator.get_next_link(),
                previous=paginator.get_previous_link(),
                results=results,
            )

            return Response(response_data.model_dump(), status=status.HTTP_200_OK)

        except Channel.DoesNotExist:
            return Response({"detail": f"Channel '{channel_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Product.DoesNotExist:
            return Response(
                {"detail": f"Product with SKU '{sku}' not found in channel '{channel_idx}'"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Retrieve product link",
        description="Get a single product link by its primary key",
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="Channel identifier",
            ),
            OpenApiParameter(
                name="sku", location=OpenApiParameter.PATH, required=True, type=str, description="Product SKU"
            ),
            OpenApiParameter(
                name="pk",
                location=OpenApiParameter.PATH,
                required=True,
                type=int,
                description="ProductLink primary key",
            ),
        ],
        responses={200: ProductLinkResponse},
    )
    def retrieve(self, request: Request, channel_idx: str, sku: str, pk: int) -> Response:
        try:
            link = get_product_link(channel_idx=channel_idx, sku=sku, pk=pk)
            return Response(_build_link_response(link).model_dump(), status=status.HTTP_200_OK)
        except Channel.DoesNotExist:
            return Response({"detail": f"Channel '{channel_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Product.DoesNotExist:
            return Response(
                {"detail": f"Product with SKU '{sku}' not found in channel '{channel_idx}'"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except ProductLink.DoesNotExist:
            return Response({"detail": f"ProductLink with pk {pk} not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Create product link",
        description="Create a new link between two products in the same channel",
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="Channel identifier",
            ),
            OpenApiParameter(
                name="sku", location=OpenApiParameter.PATH, required=True, type=str, description="Product SKU"
            ),
        ],
        request=CreateProductLinkRequest,
        responses={201: ProductLinkResponse},
    )
    def create(self, request: Request, channel_idx: str, sku: str) -> Response:
        try:
            data = CreateProductLinkRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            link = create_product_link(
                channel_idx=channel_idx,
                sku=sku,
                linked_product_sku=data.linked_product_sku,
                link_type_idx=data.link_type_idx,
                position=data.position,
            )
            return Response(_build_link_response(link).model_dump(), status=status.HTTP_201_CREATED)
        except Channel.DoesNotExist:
            return Response({"detail": f"Channel '{channel_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Product.DoesNotExist:
            return Response(
                {"detail": f"Product not found in channel '{channel_idx}'"}, status=status.HTTP_404_NOT_FOUND
            )
        except ProductLinkType.DoesNotExist:
            return Response({"detail": f"Link type '{data.link_type_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Update product link",
        description="Partially update a product link",
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="Channel identifier",
            ),
            OpenApiParameter(
                name="sku", location=OpenApiParameter.PATH, required=True, type=str, description="Product SKU"
            ),
            OpenApiParameter(
                name="pk",
                location=OpenApiParameter.PATH,
                required=True,
                type=int,
                description="ProductLink primary key",
            ),
        ],
        request=UpdateProductLinkRequest,
        responses={200: ProductLinkResponse},
    )
    def partial_update(self, request: Request, channel_idx: str, sku: str, pk: int) -> Response:
        try:
            data = UpdateProductLinkRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            fields = {k: v for k, v in data.model_dump().items() if v is not None}
            link = update_product_link(channel_idx=channel_idx, sku=sku, pk=pk, **fields)
            return Response(_build_link_response(link).model_dump(), status=status.HTTP_200_OK)
        except ProductLink.DoesNotExist:
            return Response({"detail": f"ProductLink with pk {pk} not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Delete product link",
        description="Delete a product link",
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="Channel identifier",
            ),
            OpenApiParameter(
                name="sku", location=OpenApiParameter.PATH, required=True, type=str, description="Product SKU"
            ),
            OpenApiParameter(
                name="pk",
                location=OpenApiParameter.PATH,
                required=True,
                type=int,
                description="ProductLink primary key",
            ),
        ],
        responses={200: {"description": "Deleted counts by model"}},
    )
    def destroy(self, request: Request, channel_idx: str, sku: str, pk: int) -> Response:
        try:
            deleted = delete_product_link(channel_idx=channel_idx, sku=sku, pk=pk)
            return Response({"deleted": deleted}, status=status.HTTP_200_OK)
        except ProductLink.DoesNotExist:
            return Response({"detail": f"ProductLink with pk {pk} not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

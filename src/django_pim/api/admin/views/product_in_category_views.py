# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Admin API views for product positions within categories.

DRF ViewSet for managing product ordering in categories.
"""

from django_utils.api.v2_errors import raise_pydantic_as_drf
from drf_spectacular.utils import OpenApiParameter, extend_schema
from pydantic import ValidationError
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from ....models import Channel, Product, ProductCategory, ProductInCategory
from ....schemas.requests.product_in_category import ProductPositionReorderRequest
from ....schemas.responses.product_in_category import ProductInCategoryListResponse
from ....services.product_in_category_service import list_products_in_category, reorder_products_in_category
from ..errors import internal_error
from ..permissions import IsAdminUser


class ProductInCategoryViewSet(viewsets.ViewSet):
    """ViewSet for managing product positions within a category."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="List products in category",
        description="Returns positioned (pinned) and unpositioned products for a category. "
        "Positioned products are returned in full, ordered by position. "
        "Unpositioned products are paginated.",
        tags=["Categories"],
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="Channel identifier",
            ),
            OpenApiParameter(
                name="idx", location=OpenApiParameter.PATH, required=True, type=str, description="Category idx"
            ),
            OpenApiParameter(
                name="search",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Search products by SKU",
            ),
            OpenApiParameter(
                name="page",
                location=OpenApiParameter.QUERY,
                required=False,
                type=int,
                description="Page number for unpositioned products",
            ),
            OpenApiParameter(
                name="page_size",
                location=OpenApiParameter.QUERY,
                required=False,
                type=int,
                description="Items per page for unpositioned products (default 24)",
            ),
        ],
        responses={200: ProductInCategoryListResponse, 404: {"description": "Channel or category not found"}},
    )
    def list(self, request: Request, channel_idx: str, idx: str) -> Response:
        """List products in a category with positioned/unpositioned split."""
        try:
            search = request.query_params.get("search", None)
            page = request.query_params.get("page", None)
            page_size = request.query_params.get("page_size", "24")

            page_int = int(page) if page else None
            page_size_int = min(int(page_size), 100)

            result = list_products_in_category(
                channel_idx=channel_idx, category_idx=idx, search=search, page=page_int, page_size=page_size_int
            )

            response = ProductInCategoryListResponse(**result)
            return Response(response.model_dump(), status=status.HTTP_200_OK)

        except Channel.DoesNotExist:
            return Response({"detail": f"Channel '{channel_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except ProductCategory.DoesNotExist:
            return Response(
                {"detail": f"Category '{idx}' not found in channel '{channel_idx}'"}, status=status.HTTP_404_NOT_FOUND
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Reorder products in category",
        description="Batch update product positions within a category. Set position > 0 to pin, position = 0 to unpin.",
        tags=["Categories"],
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="Channel identifier",
            ),
            OpenApiParameter(
                name="idx", location=OpenApiParameter.PATH, required=True, type=str, description="Category idx"
            ),
        ],
        request=ProductPositionReorderRequest,
        responses={
            200: {"description": "Number of products reordered"},
            400: {"description": "Validation error"},
            404: {"description": "Channel, category, or product not found"},
        },
    )
    def reorder(self, request: Request, channel_idx: str, idx: str) -> Response:
        """Batch update product positions within a category."""
        try:
            data = ProductPositionReorderRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            count = reorder_products_in_category(
                channel_idx=channel_idx, category_idx=idx, items=[item.model_dump() for item in data.items]
            )
            return Response({"reordered": count}, status=status.HTTP_200_OK)
        except (
            Channel.DoesNotExist,
            ProductCategory.DoesNotExist,
            Product.DoesNotExist,
            ProductInCategory.DoesNotExist,
        ):
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

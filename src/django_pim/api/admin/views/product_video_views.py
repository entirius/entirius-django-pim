# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Admin API views for product videos.

DRF ViewSet for managing product video assignments (YouTube/Vimeo URLs).
"""

from django_utils.api.v2_errors import raise_pydantic_as_drf
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from pydantic import ValidationError
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from ....models import Channel, Product, ProductVideo, Video
from ....models.product_video import VideoRole
from ....schemas.requests.product_video import CreateProductVideoRequest, UpdateProductVideoRequest
from ....schemas.responses.product_video import ProductVideoListResponse, ProductVideoResponse, VideoResponse
from ....services.product_video_service import (
    create_product_video,
    delete_product_video,
    get_product_video,
    list_product_videos,
    update_product_video,
)
from ..errors import internal_error
from ..pagination import AdminPageNumberPagination
from ..permissions import IsAdminUser


def _build_video_response(v: Video) -> VideoResponse:
    return VideoResponse(
        pk=v.pk,
        title=v.title,
        is_external=v.is_external,
        source=v.source,
        source_name=v.get_source_label(),
        video_url=v.video_url,
        db_created=str(v.db_created),
    )


def _build_product_video_response(pv: ProductVideo) -> ProductVideoResponse:
    return ProductVideoResponse(
        pk=pv.pk,
        video=_build_video_response(pv.video),
        video_role=pv.get_role_api_label(),
        video_role_name=VideoRole.labelFromId(pv.video_role),
        language_iso2=pv.language.iso2 if pv.language else None,
        position=pv.position,
    )


@extend_schema_view(
    list=extend_schema(tags=["Product Videos"]),
    retrieve=extend_schema(tags=["Product Videos"]),
    create=extend_schema(tags=["Product Videos"]),
    partial_update=extend_schema(tags=["Product Videos"]),
    destroy=extend_schema(tags=["Product Videos"]),
)
class ProductVideoViewSet(viewsets.ViewSet):
    """ViewSet for product video management."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="List product videos",
        description="Get a paginated list of videos for a specific product",
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
                name="role",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Filter by role (main, variant, unknown)",
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
        responses={200: ProductVideoListResponse},
    )
    def list(self, request: Request, channel_idx: str, sku: str) -> Response:
        try:
            role = request.query_params.get("role", None)
            ordering = request.query_params.get("ordering")

            qs = list_product_videos(channel_idx=channel_idx, sku=sku, role=role, ordering=ordering)

            paginator = AdminPageNumberPagination()
            paginated = paginator.paginate_queryset(qs, request)

            results = [_build_product_video_response(pv) for pv in paginated]

            response_data = ProductVideoListResponse(
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
        summary="Retrieve product video",
        description="Get a single product video assignment by its primary key",
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
                description="ProductVideo primary key",
            ),
        ],
        responses={200: ProductVideoResponse},
    )
    def retrieve(self, request: Request, channel_idx: str, sku: str, pk: int) -> Response:
        try:
            pv = get_product_video(channel_idx=channel_idx, sku=sku, pk=pk)
            return Response(_build_product_video_response(pv).model_dump(), status=status.HTTP_200_OK)
        except ProductVideo.DoesNotExist:
            return Response({"detail": f"ProductVideo with pk {pk} not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Create product video",
        description="Create a video from URL and link it to a product. Source (YouTube/Vimeo) is auto-detected.",
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
        request=CreateProductVideoRequest,
        responses={201: ProductVideoResponse},
    )
    def create(self, request: Request, channel_idx: str, sku: str) -> Response:
        try:
            data = CreateProductVideoRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            pv = create_product_video(
                channel_idx=channel_idx,
                sku=sku,
                video_url=data.video_url,
                title=data.title,
                video_role=data.video_role,
                language_iso2=data.language_iso2,
                position=data.position,
            )
            return Response(_build_product_video_response(pv).model_dump(), status=status.HTTP_201_CREATED)
        except Channel.DoesNotExist:
            return Response({"detail": f"Channel '{channel_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Product.DoesNotExist:
            return Response({"detail": f"Product with SKU '{sku}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Update product video",
        description="Partially update a product video assignment (title, role, language, position)",
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
                description="ProductVideo primary key",
            ),
        ],
        request=UpdateProductVideoRequest,
        responses={200: ProductVideoResponse},
    )
    def partial_update(self, request: Request, channel_idx: str, sku: str, pk: int) -> Response:
        try:
            data = UpdateProductVideoRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            fields = {k: v for k, v in data.model_dump().items() if v is not None}
            pv = update_product_video(channel_idx=channel_idx, sku=sku, pk=pk, **fields)
            return Response(_build_product_video_response(pv).model_dump(), status=status.HTTP_200_OK)
        except ProductVideo.DoesNotExist:
            return Response({"detail": f"ProductVideo with pk {pk} not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Delete product video",
        description="Delete a product video assignment and its Video object",
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
                description="ProductVideo primary key",
            ),
        ],
        responses={200: {"description": "Deleted counts by model"}},
    )
    def destroy(self, request: Request, channel_idx: str, sku: str, pk: int) -> Response:
        try:
            deleted = delete_product_video(channel_idx=channel_idx, sku=sku, pk=pk)
            return Response({"deleted": deleted}, status=status.HTTP_200_OK)
        except ProductVideo.DoesNotExist:
            return Response({"detail": f"ProductVideo with pk {pk} not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

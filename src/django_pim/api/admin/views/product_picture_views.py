# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Admin API views for product pictures and picture uploads.

DRF ViewSet for managing product gallery and uploading images.
"""

from django_utils.api.v2_errors import raise_pydantic_as_drf
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view, inline_serializer
from pydantic import ValidationError
from rest_framework import serializers, status, viewsets
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from ....models import Channel, Picture, Product, ProductPicture
from ....models.product_picture import PictureRole
from ....schemas.requests.product_picture import LinkPictureRequest, UpdateProductPictureRequest
from ....schemas.responses.product_picture import PictureResponse, ProductPictureListResponse, ProductPictureResponse
from ....services.product_picture_service import (
    get_product_picture,
    link_picture_to_product,
    list_product_pictures,
    unlink_picture_from_product,
    update_product_picture,
    upload_picture,
)
from ..errors import internal_error
from ..pagination import AdminPageNumberPagination
from ..permissions import IsAdminUser

MAX_PICTURE_SIZE = 10 * 1024 * 1024  # 10MB


def _build_picture_response(pic: Picture) -> PictureResponse:
    return PictureResponse(
        pk=pic.pk,
        sha1=pic.sha1,
        width=pic.width,
        height=pic.height,
        original_file_name=pic.original_file_name,
        image_url=pic.image.url if pic.image else "",
        db_created=str(pic.db_created),
    )


def _build_product_picture_response(pp: ProductPicture) -> ProductPictureResponse:
    return ProductPictureResponse(
        pk=pp.pk,
        picture=_build_picture_response(pp.picture),
        picture_role=pp.get_role_api_label(),
        picture_role_name=PictureRole.labelFromId(pp.picture_role),
        language_iso2=pp.language.iso2 if pp.language else None,
        position=pp.position,
        alt_text_t9n=pp.alt_text_t9n,
    )


class PictureUploadView(APIView):
    """Global picture upload endpoint with SHA1 deduplication."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser]

    @extend_schema(
        summary="Upload picture",
        description="Upload an image file. Returns existing picture if SHA1 matches (deduplication). Max 10MB.",
        tags=["Product Pictures"],
        request=inline_serializer(
            name="PictureUploadRequest", fields={"image": serializers.ImageField(help_text="Image file to upload")}
        ),
        responses={201: PictureResponse},
    )
    def post(self, request: Request) -> Response:
        if "image" not in request.FILES:
            return Response({"detail": "No 'image' file provided"}, status=status.HTTP_400_BAD_REQUEST)

        image_file = request.FILES["image"]
        if image_file.size > MAX_PICTURE_SIZE:
            return Response(
                {"detail": f"Image size exceeds maximum of {MAX_PICTURE_SIZE // (1024 * 1024)}MB"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            picture = upload_picture(image_file)
            return Response(_build_picture_response(picture).model_dump(), status=status.HTTP_201_CREATED)
        except Exception as e:
            return internal_error(e)


@extend_schema_view(
    list=extend_schema(tags=["Product Pictures"]),
    retrieve=extend_schema(tags=["Product Pictures"]),
    create=extend_schema(tags=["Product Pictures"]),
    partial_update=extend_schema(tags=["Product Pictures"]),
    destroy=extend_schema(tags=["Product Pictures"]),
)
class ProductPictureViewSet(viewsets.ViewSet):
    """ViewSet for product picture gallery management."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]
    parser_classes = [JSONParser, MultiPartParser]

    @extend_schema(
        summary="List product pictures",
        description="Get a paginated list of pictures for a specific product",
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
                description="Filter by role (main, general, variant, angle)",
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
        responses={200: ProductPictureListResponse},
    )
    def list(self, request: Request, channel_idx: str, sku: str) -> Response:
        try:
            role = request.query_params.get("role", None)
            ordering = request.query_params.get("ordering")

            qs = list_product_pictures(channel_idx=channel_idx, sku=sku, role=role, ordering=ordering)

            paginator = AdminPageNumberPagination()
            paginated = paginator.paginate_queryset(qs, request)

            results = [_build_product_picture_response(pp) for pp in paginated]

            response_data = ProductPictureListResponse(
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
        summary="Retrieve product picture",
        description="Get a single product picture assignment by its primary key",
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
                description="ProductPicture primary key",
            ),
        ],
        responses={200: ProductPictureResponse},
    )
    def retrieve(self, request: Request, channel_idx: str, sku: str, pk: int) -> Response:
        try:
            pp = get_product_picture(channel_idx=channel_idx, sku=sku, pk=pk)
            return Response(_build_product_picture_response(pp).model_dump(), status=status.HTTP_200_OK)
        except ProductPicture.DoesNotExist:
            return Response({"detail": f"ProductPicture with pk {pk} not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Link or upload picture to product",
        description=(
            "Two modes: (1) JSON body with picture_pk to link existing picture, "
            "(2) Multipart with 'image' file to upload and link in one step."
        ),
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
        request=LinkPictureRequest,
        responses={201: ProductPictureResponse},
    )
    def create(self, request: Request, channel_idx: str, sku: str) -> Response:
        try:
            # Multipart upload + link
            if "image" in request.FILES:
                image_file = request.FILES["image"]
                if image_file.size > MAX_PICTURE_SIZE:
                    return Response(
                        {"detail": f"Image size exceeds maximum of {MAX_PICTURE_SIZE // (1024 * 1024)}MB"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                picture = upload_picture(image_file)
                picture_role = request.data.get("picture_role", "general")
                position = int(request.data.get("position", 0))
                language_iso2 = request.data.get("language_iso2", None)
                alt_text_t9n = request.data.get("alt_text_t9n", {})

                pp = link_picture_to_product(
                    channel_idx=channel_idx,
                    sku=sku,
                    picture_pk=picture.pk,
                    picture_role=picture_role,
                    position=position,
                    language_iso2=language_iso2,
                    alt_text_t9n=alt_text_t9n if isinstance(alt_text_t9n, dict) else {},
                )
                return Response(_build_product_picture_response(pp).model_dump(), status=status.HTTP_201_CREATED)

            # JSON link existing picture
            try:
                data = LinkPictureRequest(**request.data)
            except ValidationError as exc:
                raise_pydantic_as_drf(exc)

            pp = link_picture_to_product(
                channel_idx=channel_idx,
                sku=sku,
                picture_pk=data.picture_pk,
                picture_role=data.picture_role,
                position=data.position,
                language_iso2=data.language_iso2,
                alt_text_t9n=data.alt_text_t9n,
            )
            return Response(_build_product_picture_response(pp).model_dump(), status=status.HTTP_201_CREATED)

        except Channel.DoesNotExist:
            return Response({"detail": f"Channel '{channel_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Product.DoesNotExist:
            return Response({"detail": f"Product with SKU '{sku}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Picture.DoesNotExist:
            return Response({"detail": "Picture not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Update product picture assignment",
        description="Partially update a product picture assignment (role, position, language, alt text)",
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
                description="ProductPicture primary key",
            ),
        ],
        request=UpdateProductPictureRequest,
        responses={200: ProductPictureResponse},
    )
    def partial_update(self, request: Request, channel_idx: str, sku: str, pk: int) -> Response:
        try:
            data = UpdateProductPictureRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            fields = {k: v for k, v in data.model_dump().items() if v is not None}
            pp = update_product_picture(channel_idx=channel_idx, sku=sku, pk=pk, **fields)
            return Response(_build_product_picture_response(pp).model_dump(), status=status.HTTP_200_OK)
        except ProductPicture.DoesNotExist:
            return Response({"detail": f"ProductPicture with pk {pk} not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Unlink picture from product",
        description="Remove a picture assignment from a product (does not delete the Picture itself)",
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
                description="ProductPicture primary key",
            ),
        ],
        responses={200: {"description": "Deleted counts by model"}},
    )
    def destroy(self, request: Request, channel_idx: str, sku: str, pk: int) -> Response:
        try:
            deleted = unlink_picture_from_product(channel_idx=channel_idx, sku=sku, pk=pk)
            return Response({"deleted": deleted}, status=status.HTTP_200_OK)
        except ProductPicture.DoesNotExist:
            return Response({"detail": f"ProductPicture with pk {pk} not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

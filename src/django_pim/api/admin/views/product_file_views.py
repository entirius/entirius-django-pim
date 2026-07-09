# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Admin API views for product files and file uploads.

DRF ViewSet for managing product file attachments and uploading files.
"""

import json

from django_utils.api.v2_errors import raise_pydantic_as_drf
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view, inline_serializer
from pydantic import ValidationError
from rest_framework import serializers, status, viewsets
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from ....models import Channel, Files, FilesCategory, Product, ProductFile
from ....models.files import FileRole
from ....schemas.requests.product_file import LinkFileRequest, UpdateFileRequest
from ....schemas.responses.product_file import FileResponse, ProductFileListResponse, ProductFileResponse
from ....services.files_category_service import resolve_files_category_name
from ....services.product_file_service import (
    link_file_to_product,
    list_product_files,
    unlink_file_from_product,
    update_file,
    upload_file,
)
from ..errors import internal_error
from ..pagination import AdminPageNumberPagination
from ..permissions import IsAdminUser

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def _build_file_response(f: Files) -> FileResponse:
    return FileResponse(
        pk=f.pk,
        sha1=f.sha1,
        file_type=f.file_type,
        file_type_name=FileRole.labelFromId(f.file_type),
        original_file_name=f.original_file_name,
        file_label=f.file_label,
        file_label_t9n=f.file_label_t9n or {},
        file_url=f.file.url if f.file else "",
        category_code=f.file_category.code if f.file_category else None,
        category_name=resolve_files_category_name(f.file_category) if f.file_category else None,
        db_created=str(f.db_created),
    )


def _build_product_file_response(pf: ProductFile) -> ProductFileResponse:
    return ProductFileResponse(pk=pf.pk, file=_build_file_response(pf.file))


class FileUploadView(APIView):
    """Global file upload endpoint with SHA1 deduplication."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser]

    @extend_schema(
        summary="Upload file",
        description="Upload a file. Returns existing file if SHA1 matches (deduplication). Max 50MB.",
        tags=["Product Files"],
        request=inline_serializer(
            name="FileUploadRequest",
            fields={
                "file": serializers.FileField(help_text="File to upload"),
                "file_category_code": serializers.CharField(required=False, help_text="File category code"),
                "file_label": serializers.CharField(required=False, help_text="Custom file label"),
                "file_type": serializers.CharField(
                    required=False, help_text="File type (pdf, doc, picture, video, undefined)"
                ),
            },
        ),
        responses={201: FileResponse},
    )
    def post(self, request: Request) -> Response:
        if "file" not in request.FILES:
            return Response({"detail": "No 'file' provided"}, status=status.HTTP_400_BAD_REQUEST)

        file_obj = request.FILES["file"]
        if file_obj.size > MAX_FILE_SIZE:
            return Response(
                {"detail": f"File size exceeds maximum of {MAX_FILE_SIZE // (1024 * 1024)}MB"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_label_t9n = request.data.get("file_label_t9n", None)
        if isinstance(file_label_t9n, str):
            try:
                file_label_t9n = json.loads(file_label_t9n)
            except json.JSONDecodeError:
                return Response({"detail": "Invalid JSON in file_label_t9n"}, status=status.HTTP_400_BAD_REQUEST)
            if not isinstance(file_label_t9n, dict):
                return Response({"detail": "file_label_t9n must be a JSON object"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            f = upload_file(
                file_obj=file_obj,
                file_category_code=request.data.get("file_category_code", None),
                file_label=request.data.get("file_label", None),
                file_label_t9n=file_label_t9n,
                file_type=request.data.get("file_type", None),
            )
            return Response(_build_file_response(f).model_dump(), status=status.HTTP_201_CREATED)
        except Exception as e:
            return internal_error(e)


@extend_schema_view(
    list=extend_schema(tags=["Product Files"]),
    create=extend_schema(tags=["Product Files"]),
    destroy=extend_schema(tags=["Product Files"]),
)
class ProductFileViewSet(viewsets.ViewSet):
    """ViewSet for product file attachment management."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]
    parser_classes = [JSONParser, MultiPartParser]

    @extend_schema(
        summary="List product files",
        description="Get a paginated list of files attached to a specific product",
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
        responses={200: ProductFileListResponse},
    )
    def list(self, request: Request, channel_idx: str, sku: str) -> Response:
        try:
            qs = list_product_files(channel_idx=channel_idx, sku=sku)

            paginator = AdminPageNumberPagination()
            paginated = paginator.paginate_queryset(qs, request)

            results = [_build_product_file_response(pf) for pf in paginated]

            response_data = ProductFileListResponse(
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
        summary="Link or upload file to product",
        description=(
            "Two modes: (1) JSON body with file_pk to link existing file, "
            "(2) Multipart with 'file' to upload and link in one step."
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
        request=LinkFileRequest,
        responses={201: ProductFileResponse},
    )
    def create(self, request: Request, channel_idx: str, sku: str) -> Response:
        try:
            # Multipart upload + link
            if "file" in request.FILES:
                file_obj = request.FILES["file"]
                if file_obj.size > MAX_FILE_SIZE:
                    return Response(
                        {"detail": f"File size exceeds maximum of {MAX_FILE_SIZE // (1024 * 1024)}MB"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                f = upload_file(
                    file_obj=file_obj,
                    file_category_code=request.data.get("file_category_code", None),
                    file_label=request.data.get("file_label", None),
                    file_type=request.data.get("file_type", None),
                )
                pf = link_file_to_product(channel_idx=channel_idx, sku=sku, file_pk=f.pk)
                return Response(_build_product_file_response(pf).model_dump(), status=status.HTTP_201_CREATED)

            # JSON link existing file
            try:
                data = LinkFileRequest(**request.data)
            except ValidationError as exc:
                raise_pydantic_as_drf(exc)

            pf = link_file_to_product(channel_idx=channel_idx, sku=sku, file_pk=data.file_pk)
            return Response(_build_product_file_response(pf).model_dump(), status=status.HTTP_201_CREATED)

        except Channel.DoesNotExist:
            return Response({"detail": f"Channel '{channel_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Product.DoesNotExist:
            return Response({"detail": f"Product with SKU '{sku}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Files.DoesNotExist:
            return Response({"detail": "File not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Unlink file from product",
        description="Remove a file attachment from a product (does not delete the File itself)",
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
                description="ProductFile primary key",
            ),
        ],
        responses={200: {"description": "Deleted counts by model"}},
    )
    def destroy(self, request: Request, channel_idx: str, sku: str, pk: int) -> Response:
        try:
            deleted = unlink_file_from_product(channel_idx=channel_idx, sku=sku, pk=pk)
            return Response({"deleted": deleted}, status=status.HTTP_200_OK)
        except ProductFile.DoesNotExist:
            return Response({"detail": f"ProductFile with pk {pk} not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)


class FileUpdateView(APIView):
    """Update file metadata (label, category)."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Update file metadata",
        description="Update file label (t9n) and/or category assignment.",
        tags=["Product Files"],
        request=UpdateFileRequest,
        responses={200: FileResponse},
    )
    def patch(self, request: Request, pk: int) -> Response:
        try:
            data = UpdateFileRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        kwargs = {}
        if data.file_label_t9n is not None:
            kwargs["file_label_t9n"] = data.file_label_t9n
        if "file_category_code" in request.data:
            kwargs["file_category_code"] = data.file_category_code

        try:
            f = update_file(pk=pk, **kwargs)
            return Response(_build_file_response(f).model_dump(), status=status.HTTP_200_OK)
        except Files.DoesNotExist:
            return Response({"detail": f"File with pk {pk} not found"}, status=status.HTTP_404_NOT_FOUND)
        except FilesCategory.DoesNotExist:
            return Response(
                {"detail": f"Category code '{data.file_category_code}' not found"}, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return internal_error(e)

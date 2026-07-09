# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Admin API views for file categories.

DRF ViewSet for administrative file category CRUD operations.
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
    from ....models import FilesCategory
from ....schemas.requests.files_category import CreateFilesCategoryRequest, UpdateFilesCategoryRequest
from ....schemas.responses.files_category import FilesCategoryListResponse, FilesCategoryResponse
from ....services.files_category_service import (
    create_files_category,
    delete_files_category,
    get_files_category_by_code,
    list_files_categories,
    resolve_files_category_name,
    update_files_category,
)
from ..errors import internal_error, not_found_response
from ..pagination import AdminPageNumberPagination
from ..permissions import IsAdminUser


def _build_category_response(cat: FilesCategory) -> FilesCategoryResponse:
    return FilesCategoryResponse(
        pk=cat.pk,
        code=cat.code,
        name_t9n=cat.name_t9n,
        name=resolve_files_category_name(cat),
        db_created=str(cat.db_created),
    )


@extend_schema_view(
    list=extend_schema(tags=["Files Categories"]),
    retrieve=extend_schema(tags=["Files Categories"]),
    create=extend_schema(tags=["Files Categories"]),
    partial_update=extend_schema(tags=["Files Categories"]),
    destroy=extend_schema(tags=["Files Categories"]),
)
class FilesCategoryViewSet(viewsets.ViewSet):
    """ViewSet for file category management."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="List files categories",
        description="Get a paginated list of file categories",
        parameters=[
            OpenApiParameter(
                name="search",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Search by code or name",
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
        responses={200: FilesCategoryListResponse},
    )
    def list(self, request: Request) -> Response:
        try:
            search = request.query_params.get("search", None)
            ordering = request.query_params.get("ordering")

            qs = list_files_categories(search=search, ordering=ordering)

            paginator = AdminPageNumberPagination()
            paginated = paginator.paginate_queryset(qs, request)

            results = [_build_category_response(cat) for cat in paginated]

            response_data = FilesCategoryListResponse(
                count=qs.count(),
                next=paginator.get_next_link(),
                previous=paginator.get_previous_link(),
                results=results,
            )

            return Response(response_data.model_dump(), status=status.HTTP_200_OK)

        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Retrieve files category by code",
        description="Get a single file category by its code",
        parameters=[
            OpenApiParameter(
                name="code", location=OpenApiParameter.PATH, required=True, type=str, description="Category code"
            )
        ],
        responses={200: FilesCategoryResponse},
    )
    def retrieve(self, request: Request, code: str) -> Response:
        try:
            cat = get_files_category_by_code(code=code)
            return Response(_build_category_response(cat).model_dump(), status=status.HTTP_200_OK)
        except ObjectDoesNotExist:
            return not_found_response(f"FilesCategory with code '{code}' not found")
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Create files category",
        description="Create a new file category",
        request=CreateFilesCategoryRequest,
        responses={201: FilesCategoryResponse},
    )
    def create(self, request: Request) -> Response:
        try:
            data = CreateFilesCategoryRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            cat = create_files_category(code=data.code, name_t9n=data.name_t9n)
            return Response(_build_category_response(cat).model_dump(), status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Update files category",
        description="Partially update a file category by its code",
        parameters=[
            OpenApiParameter(
                name="code", location=OpenApiParameter.PATH, required=True, type=str, description="Category code"
            )
        ],
        request=UpdateFilesCategoryRequest,
        responses={200: FilesCategoryResponse},
    )
    def partial_update(self, request: Request, code: str) -> Response:
        try:
            data = UpdateFilesCategoryRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            fields = {k: v for k, v in data.model_dump().items() if v is not None}
            cat = update_files_category(code=code, **fields)
            return Response(_build_category_response(cat).model_dump(), status=status.HTTP_200_OK)
        except ObjectDoesNotExist:
            return not_found_response(f"FilesCategory with code '{code}' not found")
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Delete files category",
        description="Delete a file category by its code",
        parameters=[
            OpenApiParameter(
                name="code", location=OpenApiParameter.PATH, required=True, type=str, description="Category code"
            )
        ],
        responses={200: {"description": "Deleted counts by model"}},
    )
    def destroy(self, request: Request, code: str) -> Response:
        try:
            deleted = delete_files_category(code=code)
            return Response({"deleted": deleted}, status=status.HTTP_200_OK)
        except ObjectDoesNotExist:
            return not_found_response(f"FilesCategory with code '{code}' not found")
        except Exception as e:
            return internal_error(e)

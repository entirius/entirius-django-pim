# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Admin API views for categories.

DRF ViewSet for administrative product category CRUD operations.
"""

from django.core.exceptions import ObjectDoesNotExist
from django_utils.api.v2_errors import raise_pydantic_as_drf
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from pydantic import ValidationError
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from ....models import Channel, ProductCategory
from ....schemas import CategoryDetailResponse, CategoryListResponse, CategoryResponse
from ....schemas.requests import CategoryReorderRequest, CreateCategoryRequest, UpdateCategoryRequest
from ....services import (
    create_category,
    delete_category,
    get_category_detail,
    list_categories,
    reorder_categories,
    update_category,
)
from ..errors import internal_error
from ..pagination import AdminPageNumberPagination
from ..permissions import IsAdminUser


def _build_category_detail_response(category: ProductCategory) -> CategoryDetailResponse:
    """Build a full detail response from a category with annotations."""
    return CategoryDetailResponse(
        pk=category.pk,
        idx=category.idx,
        name=category.name,
        name_t9n=category.name_t9n,
        desc=category.desc,
        description_t9n=category.description_t9n,
        meta_title_t9n=category.meta_title_t9n,
        meta_description_t9n=category.meta_description_t9n,
        canonical_url_t9n=category.canonical_url_t9n,
        image_url=category.image_url,
        og_image_url=category.og_image_url,
        noindex=category.noindex,
        nofollow=category.nofollow,
        url_key_t9n=category.url_key_t9n,
        parent_category=category.parent_category_id,
        parent_category_idx=category.parent_category.idx if category.parent_category else None,
        breadcrumb_path=category.breadcrumb_path,
        tree_deep=category.tree_deep,
        position=category.position,
        is_active=category.is_active,
        is_in_menu=category.is_in_menu,
        product_count=getattr(category, "product_count", 0),
        subcategory_count=getattr(category, "subcategory_count", 0),
    )


@extend_schema_view(
    list=extend_schema(tags=["Categories"]),
    retrieve=extend_schema(tags=["Categories"]),
    create=extend_schema(tags=["Categories"]),
    partial_update=extend_schema(tags=["Categories"]),
    destroy=extend_schema(tags=["Categories"]),
    reorder=extend_schema(tags=["Categories"]),
)
class CategoryViewSet(viewsets.ViewSet):
    """ViewSet for category CRUD operations within a channel context."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]
    access_area = "pim.categories"

    @extend_schema(
        summary="List categories",
        description="Get a paginated, searchable list of categories for a specific channel",
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="Channel identifier",
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
            OpenApiParameter(
                name="search",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Search categories by name",
            ),
            OpenApiParameter(
                name="is_active",
                location=OpenApiParameter.QUERY,
                required=False,
                type=bool,
                description="Filter by active status",
            ),
            OpenApiParameter(
                name="parent_category",
                location=OpenApiParameter.QUERY,
                required=False,
                type=int,
                description="Filter by parent category ID",
            ),
            OpenApiParameter(
                name="root_only",
                location=OpenApiParameter.QUERY,
                required=False,
                type=bool,
                description="Return only root categories (no parent)",
            ),
            OpenApiParameter(
                name="ordering",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Order results by field (e.g., 'name', '-name', 'idx')",
            ),
        ],
        responses={200: CategoryListResponse},
    )
    def list(self, request: Request, channel_idx: str) -> Response:
        """List categories for a shop with filtering and pagination."""
        try:
            search = request.query_params.get("search", None)
            is_active_param = request.query_params.get("is_active", None)
            parent_category_param = request.query_params.get("parent_category", None)
            root_only_param = request.query_params.get("root_only", None)
            ordering = request.query_params.get("ordering", None)

            is_active = None
            if is_active_param is not None:
                is_active = is_active_param.lower() in ("true", "1", "yes")

            root_only = False
            if root_only_param is not None:
                root_only = root_only_param.lower() in ("true", "1", "yes")

            parent_category_id = None
            if parent_category_param is not None:
                try:
                    parent_category_id = int(parent_category_param)
                except ValueError:
                    return Response(
                        {"detail": "Invalid parent_category parameter: must be an integer"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            categories_qs = list_categories(
                channel_idx=channel_idx,
                search=search,
                is_active=is_active,
                parent_category_id=parent_category_id,
                root_only=root_only,
                ordering=ordering,
            )

            paginator = AdminPageNumberPagination()
            paginated_categories = paginator.paginate_queryset(categories_qs, request)

            category_responses = [
                CategoryResponse(
                    pk=c.pk,
                    idx=c.idx,
                    name=c.name,
                    parent_category=c.parent_category_id,
                    is_active=c.is_active,
                    is_in_menu=c.is_in_menu,
                    url_key=c.url_key,
                    product_count=getattr(c, "product_count", 0),
                    desc=c.desc,
                )
                for c in paginated_categories
            ]

            response_data = CategoryListResponse(
                count=paginator.page.paginator.count,
                next=paginator.get_next_link(),
                previous=paginator.get_previous_link(),
                results=category_responses,
            )

            return Response(response_data.model_dump(), status=status.HTTP_200_OK)

        except Channel.DoesNotExist:
            return Response({"detail": f"Channel '{channel_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Retrieve category by idx",
        description="Get full category details by idx for a specific channel",
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
        responses={200: CategoryDetailResponse},
    )
    def retrieve(self, request: Request, channel_idx: str, idx: str) -> Response:
        """Retrieve a single category by idx with full detail."""
        try:
            category = get_category_detail(channel_idx=channel_idx, idx=idx)
            return Response(_build_category_detail_response(category).model_dump(), status=status.HTTP_200_OK)
        except ProductCategory.DoesNotExist:
            return Response(
                {"detail": f"Category with idx '{idx}' not found in channel '{channel_idx}'"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Channel.DoesNotExist:
            return Response({"detail": f"Channel '{channel_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Create category",
        description="Create a new category in a channel",
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="Channel identifier",
            )
        ],
        request=CreateCategoryRequest,
        responses={201: CategoryDetailResponse},
    )
    def create(self, request: Request, channel_idx: str) -> Response:
        """Create a new category."""
        try:
            data = CreateCategoryRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            category = create_category(
                channel_idx=channel_idx,
                idx=data.idx,
                name_t9n=data.name_t9n,
                desc=data.desc,
                description_t9n=data.description_t9n,
                meta_title_t9n=data.meta_title_t9n,
                meta_description_t9n=data.meta_description_t9n,
                canonical_url_t9n=data.canonical_url_t9n,
                image_url=data.image_url,
                og_image_url=data.og_image_url,
                noindex=data.noindex,
                nofollow=data.nofollow,
                parent_category_idx=data.parent_category_idx,
                position=data.position,
                is_active=data.is_active,
                is_in_menu=data.is_in_menu,
            )
            # Re-fetch with annotations for detail response
            category = get_category_detail(channel_idx=channel_idx, idx=category.idx)
            return Response(_build_category_detail_response(category).model_dump(), status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Channel.DoesNotExist:
            return Response({"detail": f"Channel '{channel_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except ProductCategory.DoesNotExist:
            return Response({"detail": "Category not found"}, status=status.HTTP_404_NOT_FOUND)
        except ObjectDoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Update category",
        description="Partially update a category. Validates against circular parent references.",
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
        request=UpdateCategoryRequest,
        responses={200: CategoryDetailResponse},
    )
    def partial_update(self, request: Request, channel_idx: str, idx: str) -> Response:
        """Partially update a category by idx."""
        try:
            data = UpdateCategoryRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            fields = {k: v for k, v in data.model_dump().items() if v is not None}
            update_category(channel_idx=channel_idx, idx=idx, **fields)
            # Re-fetch with annotations
            category = get_category_detail(channel_idx=channel_idx, idx=idx)
            return Response(_build_category_detail_response(category).model_dump(), status=status.HTTP_200_OK)
        except ProductCategory.DoesNotExist:
            return Response(
                {"detail": f"Category '{idx}' not found in channel '{channel_idx}'"}, status=status.HTTP_404_NOT_FOUND
            )
        except Channel.DoesNotExist:
            return Response({"detail": f"Channel '{channel_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except ObjectDoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Delete category",
        description="Delete a category. CASCADE deletes subcategories and product-category assignments.",
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
        responses={200: {"description": "Deleted object counts"}},
    )
    def destroy(self, request: Request, channel_idx: str, idx: str) -> Response:
        """Delete a category by idx."""
        try:
            result = delete_category(channel_idx=channel_idx, idx=idx)
            return Response(result, status=status.HTTP_200_OK)
        except ProductCategory.DoesNotExist:
            return Response(
                {"detail": f"Category '{idx}' not found in channel '{channel_idx}'"}, status=status.HTTP_404_NOT_FOUND
            )
        except Channel.DoesNotExist:
            return Response({"detail": f"Channel '{channel_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Reorder categories",
        description="Batch update position and parent for multiple categories within a channel",
        tags=["Categories"],
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="Channel identifier",
            )
        ],
        request=CategoryReorderRequest,
        responses={
            200: {"description": "Number of categories reordered"},
            400: {"description": "Validation error"},
            404: {"description": "Channel or category not found"},
        },
    )
    def reorder(self, request: Request, channel_idx: str) -> Response:
        """Batch reorder categories by updating position and parent."""
        try:
            data = CategoryReorderRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            count = reorder_categories(channel_idx=channel_idx, items=[item.model_dump() for item in data.items])
            return Response({"reordered": count}, status=status.HTTP_200_OK)
        except (ProductCategory.DoesNotExist, Channel.DoesNotExist):
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Admin API views for products.

DRF ViewSet for administrative product CRUD operations.
"""

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django_utils.api.v2_errors import raise_pydantic_as_drf
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema, extend_schema_view
from pydantic import ValidationError
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from ....models import Channel, Feature, Product
from ....schemas import (
    ProductAttributeValueResponse,
    ProductCategoryBriefResponse,
    ProductDetailResponse,
    ProductListResponse,
    ProductResponse,
)
from ....schemas.requests import BulkProductUpdateRequest, CreateProductRequest, UpdateProductRequest
from ....schemas.requests.inheritance import (
    AddToChannelRequest,
    CopyAttributesRequest,
    ToggleLanguageOverrideRequest,
    ToggleMediaOverrideRequest,
)
from ....services import (
    add_product_to_channel,
    build_product_detail_data,
    bulk_update_products,
    copy_translations,
    create_product,
    delete_product,
    get_channel_language,
    get_product_detail,
    list_products,
    lookup_bridge,
    toggle_language_override,
    toggle_media_override,
    update_product,
)
from ..errors import internal_error
from ..pagination import AdminPageNumberPagination
from ..permissions import IsAdminUser


def _build_product_detail_response(product: Product, language: str | None = None) -> ProductDetailResponse:
    """Build a full detail response from a product with prefetched relations."""
    data = build_product_detail_data(product, language=language)
    data["categories"] = [ProductCategoryBriefResponse(**c) for c in data["categories"]]
    data["attributes"] = [ProductAttributeValueResponse(**a) for a in data["attributes"]]
    return ProductDetailResponse(**data)


@extend_schema_view(
    list=extend_schema(tags=["Products"]),
    retrieve=extend_schema(tags=["Products"]),
    create=extend_schema(tags=["Products"]),
    partial_update=extend_schema(tags=["Products"]),
    destroy=extend_schema(tags=["Products"]),
)
class ProductViewSet(viewsets.ViewSet):
    """ViewSet for product CRUD operations within a channel context."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="List products",
        description="Get a paginated, searchable list of products for a specific channel",
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
                description="Search products by name, SKU, or EAN",
            ),
            OpenApiParameter(
                name="is_enabled",
                location=OpenApiParameter.QUERY,
                required=False,
                type=bool,
                description="Filter by enabled status",
            ),
            OpenApiParameter(
                name="ordering",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Order results by field (e.g., 'sku', '-sku', 'visibility')",
            ),
            OpenApiParameter(
                name="visibility",
                location=OpenApiParameter.QUERY,
                required=False,
                type=int,
                description="Filter by visibility (1=Not visible, 2=Catalog, 3=Search, 4=Catalog & Search)",
            ),
            OpenApiParameter(
                name="product_class",
                location=OpenApiParameter.QUERY,
                required=False,
                type=int,
                description="Filter by product class (1=Simple, 2=Configurable, 3=Bundle)",
            ),
            OpenApiParameter(
                name="category",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Filter by category idx",
            ),
            OpenApiParameter(
                name="has_media",
                location=OpenApiParameter.QUERY,
                required=False,
                type=bool,
                description="Filter by presence of main product picture",
            ),
            OpenApiParameter(
                name="gap_severity",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Filter by worst quality-gap severity: critical | warning",
            ),
            OpenApiParameter(
                name="attr_{feature_idx}",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Filter by attribute value. Use attr_ prefix followed by feature idx as param name, attribute idx as value. Multiple attr_ params are ANDed. Example: ?attr_color=red&attr_material=wood",
            ),
        ],
        responses={200: ProductListResponse},
        examples=[
            OpenApiExample(
                name="Product list",
                summary="Paginated product list",
                description="A typical page of products in the default-europe channel.",
                value={
                    "count": 142,
                    "next": "http://localhost:8000/api/pim/v2/admin/default-europe/products/?page=2",
                    "previous": None,
                    "results": [
                        {
                            "pk": 1,
                            "sku": "CHAIR-001",
                            "name": "Ergonomic Office Chair",
                            "visibility": "Catalog & Search",
                            "visibility_int": 4,
                            "is_enabled": True,
                            "product_class": 1,
                            "product_class_name": "Simple",
                            "feature_set_idx": "furniture",
                            "thumbnail_url": "/media/thumbs/chair-001/160x160.webp",
                        },
                        {
                            "pk": 2,
                            "sku": "DESK-002",
                            "name": "Standing Desk Pro",
                            "visibility": "Catalog",
                            "visibility_int": 2,
                            "is_enabled": True,
                            "product_class": 1,
                            "product_class_name": "Simple",
                            "feature_set_idx": "furniture",
                            "thumbnail_url": None,
                        },
                    ],
                },
                response_only=True,
                status_codes=["200"],
            )
        ],
    )
    def list(self, request: Request, channel_idx: str) -> Response:
        """List products for a shop with filtering and pagination."""
        try:
            search = request.query_params.get("search", None)
            is_enabled_param = request.query_params.get("is_enabled", None)
            ordering = request.query_params.get("ordering", None)

            is_enabled = None
            if is_enabled_param is not None:
                is_enabled = is_enabled_param.lower() in ("true", "1", "yes")

            visibility_param = request.query_params.get("visibility", None)
            visibility = int(visibility_param) if visibility_param else None

            product_class_param = request.query_params.get("product_class", None)
            product_class_val = int(product_class_param) if product_class_param else None

            category = request.query_params.get("category", None)

            has_media_param = request.query_params.get("has_media", None)
            has_media = None
            if has_media_param is not None:
                has_media = has_media_param.lower() in ("true", "1", "yes")

            gap_severity = request.query_params.get("gap_severity", None)

            attribute_filters = {}
            for key, value in request.query_params.items():
                if key.startswith("attr_") and value:
                    attribute_filters[key[5:]] = value

            products_qs = list_products(
                channel_idx=channel_idx,
                search=search,
                is_enabled=is_enabled,
                ordering=ordering,
                visibility=visibility,
                product_class=product_class_val,
                category_idx=category,
                has_media=has_media,
                attribute_filters=attribute_filters or None,
                gap_severity=gap_severity,
            )

            paginator = AdminPageNumberPagination()
            paginated_products = paginator.paginate_queryset(products_qs, request)

            media_url = getattr(settings, "MEDIA_URL", "/media/")

            product_responses = [
                ProductResponse(
                    pk=p.pk,
                    sku=p.sku,
                    name=p.name,
                    visibility=p.visibility_name,
                    visibility_int=p.visibility,
                    is_enabled=p.is_enabled,
                    product_class=p.product_class,
                    product_class_name=p.product_class_name,
                    feature_set_idx=p.feature_set.idx,
                    thumbnail_url=f"{media_url}{p._main_picture_path}" if p._main_picture_path else None,
                    gap_worst_severity=p.gap_worst_severity,
                    gap_count=p.gap_count,
                    gap_evaluated_at=p.gap_evaluated_at.isoformat() if p.gap_evaluated_at else None,
                )
                for p in paginated_products
            ]

            response_data = ProductListResponse(
                count=products_qs.count(),
                next=paginator.get_next_link(),
                previous=paginator.get_previous_link(),
                results=product_responses,
            )

            return Response(response_data.model_dump(), status=status.HTTP_200_OK)

        except Channel.DoesNotExist:
            return Response({"detail": f"Channel '{channel_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Retrieve product by SKU",
        description="Get full product details by SKU for a specific channel",
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
        responses={200: ProductDetailResponse},
        examples=[
            OpenApiExample(
                name="Product detail",
                summary="Full product detail",
                description="Complete product with attributes, categories, and inheritance info.",
                value={
                    "pk": 1,
                    "sku": "CHAIR-001",
                    "name": "Ergonomic Office Chair",
                    "name_t9n": {"en": "Ergonomic Office Chair", "pl": "Ergonomiczne Krzesło Biurowe"},
                    "description_t9n": {
                        "en": "Premium ergonomic chair with lumbar support.",
                        "pl": "Krzesło ergonomiczne z podparciem lędźwiowym.",
                    },
                    "visibility": 4,
                    "visibility_name": "Catalog & Search",
                    "is_enabled": True,
                    "product_class": 1,
                    "product_class_name": "Simple",
                    "feature_set_idx": "furniture",
                    "weight": "12.500",
                    "width": "65.000",
                    "height": "120.000",
                    "deep": "60.000",
                    "ean": "5901234123457",
                    "kind_of_product": "",
                    "inherit_attributes": False,
                    "inherit_descriptions": False,
                    "inherit_images": False,
                    "default_channel_idx": "default-europe",
                    "present_in_channels": ["default-europe", "pl-store"],
                    "inheriting_channels_count": 0,
                    "categories": [
                        {
                            "pk": 10,
                            "idx": "office-furniture",
                            "name": "Office Furniture",
                            "breadcrumb_path": "Furniture > Office Furniture",
                        }
                    ],
                    "attributes": [
                        {
                            "feature_idx": "color",
                            "feature_name": "Color",
                            "feature_type": 7,
                            "feature_type_name": "Select",
                            "value_bool": None,
                            "value_decimal": None,
                            "value_txt": "black",
                            "value_txt_t9n": None,
                            "value_json": None,
                            "value_datetime": None,
                            "attribute_idx": "black",
                            "attribute_name": "Black",
                            "overridden_langs": [],
                            "inherited_values": None,
                        }
                    ],
                },
                response_only=True,
                status_codes=["200"],
            )
        ],
    )
    def retrieve(self, request: Request, channel_idx: str, sku: str) -> Response:
        """Retrieve a single product by SKU with full detail."""
        try:
            product = get_product_detail(channel_idx=channel_idx, sku=sku)
            return Response(
                _build_product_detail_response(product, language=get_channel_language(channel_idx)).model_dump(),
                status=status.HTTP_200_OK,
            )
        except Product.DoesNotExist:
            return Response(
                {"detail": f"Product with SKU '{sku}' not found in channel '{channel_idx}'"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Channel.DoesNotExist:
            return Response({"detail": f"Channel '{channel_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Create product",
        description="Create a new product in a channel. RealProduct is get_or_created by SKU (shared across channels).",
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="Channel identifier",
            )
        ],
        request=CreateProductRequest,
        responses={201: ProductDetailResponse},
    )
    def create(self, request: Request, channel_idx: str) -> Response:
        """Create a new product."""
        try:
            data = CreateProductRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            language = get_channel_language(channel_idx)
            # Advisory duplicate check BEFORE the create: it must not run inside the create's
            # transaction, and its answer describes the catalogs as they were without this product.
            duplicates, lookup_warnings = lookup_bridge.possible_duplicates(data, language, request.user)
            product = create_product(
                channel_idx=channel_idx,
                sku=data.sku,
                feature_set_idx=data.feature_set_idx,
                visibility=data.visibility,
                is_enabled=data.is_enabled,
                product_class=data.product_class,
                ean=data.ean,
                weight=data.weight,
                width=data.width,
                height=data.height,
                deep=data.deep,
                kind_of_product=data.kind_of_product,
                attributes=[a.model_dump() for a in data.attributes] if data.attributes else None,
                category_idxs=data.category_idxs if data.category_idxs else None,
            )
            # Re-fetch with prefetched relations for detail response
            product = get_product_detail(channel_idx=channel_idx, sku=product.sku)
            detail = _build_product_detail_response(product, language=language)
            detail.possible_duplicates = duplicates
            detail.lookup_warnings = lookup_warnings
            return Response(detail.model_dump(), status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Channel.DoesNotExist:
            return Response({"detail": f"Channel '{channel_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except ObjectDoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Update product",
        description="Partially update a product. RealProduct fields (weight, EAN, etc.) are shared across all channels using this SKU.",
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
        request=UpdateProductRequest,
        responses={200: ProductDetailResponse},
    )
    def partial_update(self, request: Request, channel_idx: str, sku: str) -> Response:
        """Partially update a product by SKU."""
        try:
            data = UpdateProductRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            fields = data.model_dump(exclude_unset=True)

            product = update_product(channel_idx=channel_idx, sku=sku, **fields)
            product = get_product_detail(channel_idx=channel_idx, sku=sku)
            return Response(
                _build_product_detail_response(product, language=get_channel_language(channel_idx)).model_dump(),
                status=status.HTTP_200_OK,
            )
        except Product.DoesNotExist:
            return Response(
                {"detail": f"Product '{sku}' not found in channel '{channel_idx}'"}, status=status.HTTP_404_NOT_FOUND
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
        summary="Delete product",
        description="Delete a product from a channel. The RealProduct (shared SKU record) is NOT deleted.",
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
        responses={200: {"description": "Deleted object counts"}},
    )
    def destroy(self, request: Request, channel_idx: str, sku: str) -> Response:
        """Delete a product by SKU."""
        try:
            result = delete_product(channel_idx=channel_idx, sku=sku)
            return Response(result, status=status.HTTP_200_OK)
        except Product.DoesNotExist:
            return Response(
                {"detail": f"Product '{sku}' not found in channel '{channel_idx}'"}, status=status.HTTP_404_NOT_FOUND
            )
        except Channel.DoesNotExist:
            return Response({"detail": f"Channel '{channel_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        tags=["Products"],
        summary="Bulk update products",
        description="Update multiple products at once. Supports enabling/disabling, visibility changes, and category add/remove.",
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="Channel identifier",
            )
        ],
        request=BulkProductUpdateRequest,
        responses={200: {"description": "Number of updated products"}},
    )
    def bulk_update(self, request: Request, channel_idx: str) -> Response:
        """Bulk update multiple products."""
        try:
            data = BulkProductUpdateRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            result = bulk_update_products(
                channel_idx=channel_idx,
                skus=data.skus,
                is_enabled=data.is_enabled,
                visibility=data.visibility,
                category_idxs_add=data.category_idxs_add,
                category_idxs_remove=data.category_idxs_remove,
            )
            return Response(result, status=status.HTTP_200_OK)
        except Channel.DoesNotExist:
            return Response({"detail": f"Channel '{channel_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        tags=["Products"],
        summary="Copy attributes from another channel",
        description="One-time copy of attribute values from a source channel. Copied languages are marked as overridden.",
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
        request=CopyAttributesRequest,
        responses={200: ProductDetailResponse},
    )
    def copy_attributes_action(self, request: Request, channel_idx: str, sku: str) -> Response:
        """Copy attributes from another channel's product."""
        try:
            data = CopyAttributesRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            if data.source_channel_idx == channel_idx:
                return Response(
                    {"detail": "Source and target channels cannot be the same"}, status=status.HTTP_400_BAD_REQUEST
                )

            target_product = get_product_detail(channel_idx=channel_idx, sku=sku)
            source_product = get_product_detail(channel_idx=data.source_channel_idx, sku=sku)

            copy_translations(source_product=source_product, target_product=target_product, languages=data.languages)

            product = get_product_detail(channel_idx=channel_idx, sku=sku)
            return Response(
                _build_product_detail_response(product, language=get_channel_language(channel_idx)).model_dump(),
                status=status.HTTP_200_OK,
            )

        except Product.DoesNotExist:
            return Response({"detail": f"Product '{sku}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Channel.DoesNotExist:
            return Response({"detail": "Channel not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    # Backward-compatible alias
    copy_translations_action = copy_attributes_action

    @extend_schema(
        tags=["Products"],
        summary="Add product to another channel",
        description="Create the same product (by SKU) in another channel. Optionally copies content and/or enables inheritance flags.",
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=True,
                type=str,
                description="Source channel identifier",
            ),
            OpenApiParameter(
                name="sku", location=OpenApiParameter.PATH, required=True, type=str, description="Product SKU"
            ),
        ],
        request=AddToChannelRequest,
        responses={201: ProductDetailResponse},
    )
    def add_to_channel(self, request: Request, channel_idx: str, sku: str) -> Response:
        """Add product to another channel."""
        try:
            data = AddToChannelRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            source_product = get_product_detail(channel_idx=channel_idx, sku=sku)
            new_product = add_product_to_channel(
                source_product=source_product,
                target_channel_idx=data.target_channel_idx,
                copy_content=data.copy_content,
                inherit_attributes=data.inherit_attributes,
                inherit_descriptions=data.inherit_descriptions,
                inherit_images=data.inherit_images,
            )
            product = get_product_detail(channel_idx=data.target_channel_idx, sku=new_product.sku)
            return Response(
                _build_product_detail_response(product, language=get_channel_language(channel_idx)).model_dump(),
                status=status.HTTP_201_CREATED,
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        except Product.DoesNotExist:
            return Response(
                {"detail": f"Product '{sku}' not found in channel '{channel_idx}'"}, status=status.HTTP_404_NOT_FOUND
            )
        except Channel.DoesNotExist:
            return Response({"detail": "Channel not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        tags=["Products"],
        summary="Toggle language override",
        description="Toggle a single language between inherited/overridden for one attribute.",
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
        request=ToggleLanguageOverrideRequest,
        responses={200: ProductDetailResponse},
    )
    def toggle_override(self, request: Request, channel_idx: str, sku: str) -> Response:
        """Toggle language override for a product attribute."""
        try:
            data = ToggleLanguageOverrideRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            product = get_product_detail(channel_idx=channel_idx, sku=sku)
            toggle_language_override(
                product=product, feature_idx=data.feature_idx, language=data.language, override=data.override
            )
            product = get_product_detail(channel_idx=channel_idx, sku=sku)
            return Response(
                _build_product_detail_response(product, language=get_channel_language(channel_idx)).model_dump(),
                status=status.HTTP_200_OK,
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Product.DoesNotExist:
            return Response({"detail": f"Product '{sku}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Channel.DoesNotExist:
            return Response({"detail": f"Channel '{channel_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Feature.DoesNotExist:
            return Response({"detail": f"Feature '{data.feature_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        tags=["Products"],
        summary="Toggle media override",
        description="Toggle a media item (picture/video/file) between inherited and local.",
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
        request=ToggleMediaOverrideRequest,
        responses={200: ProductDetailResponse},
    )
    def toggle_media_override_action(self, request: Request, channel_idx: str, sku: str) -> Response:
        """Toggle media override for a product."""
        try:
            data = ToggleMediaOverrideRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            product = get_product_detail(channel_idx=channel_idx, sku=sku)
            toggle_media_override(
                product=product,
                picture_id=data.picture_id,
                video_id=data.video_id,
                file_id=data.file_id,
                override=data.override,
            )
            product = get_product_detail(channel_idx=channel_idx, sku=sku)
            return Response(
                _build_product_detail_response(product, language=get_channel_language(channel_idx)).model_dump(),
                status=status.HTTP_200_OK,
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Product.DoesNotExist:
            return Response({"detail": f"Product '{sku}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Channel.DoesNotExist:
            return Response({"detail": f"Channel '{channel_idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

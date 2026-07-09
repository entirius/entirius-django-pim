# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Admin API views for features.

DRF ViewSet for administrative feature CRUD operations.
"""

from django.core.exceptions import ObjectDoesNotExist
from django_utils.api.v2_errors import raise_pydantic_as_drf
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from pydantic import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from ....schemas import AttributeListResponse, AttributeResponse, FeatureListResponse, FeatureResponse
from ....schemas.requests import CreateFeatureRequest, UpdateFeatureRequest
from ....services import (
    build_feature_response,
    create_feature,
    delete_feature,
    get_channel_language,
    get_feature_by_idx,
    list_attributes_for_feature,
    list_features,
    resolve_attribute_name,
    update_feature,
)
from ..errors import internal_error, not_found_response
from ..pagination import AdminPageNumberPagination
from ..permissions import IsAdminUser


@extend_schema_view(
    list=extend_schema(tags=["Features"]),
    retrieve=extend_schema(tags=["Features"]),
    create=extend_schema(tags=["Features"]),
    partial_update=extend_schema(tags=["Features"]),
    destroy=extend_schema(tags=["Features"]),
    attributes=extend_schema(tags=["Features"]),
)
class FeatureViewSet(viewsets.ViewSet):
    """
    ViewSet for feature management operations.

    Provides CRUD and nested attributes endpoints for features.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="List features",
        description="Get a paginated, searchable list of features with filtering options",
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=False,
                type=str,
                description="Channel identifier (optional, for shop-scoped features)",
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
                description="Search features by idx",
            ),
            OpenApiParameter(
                name="scope",
                location=OpenApiParameter.QUERY,
                required=False,
                type=int,
                description="Filter by scope (1=SYSTEM, 2=GLOBAL, 3=BUSINESS_UNIT)",
            ),
            OpenApiParameter(
                name="feature_type",
                location=OpenApiParameter.QUERY,
                required=False,
                type=int,
                description="Filter by feature type enum value",
            ),
            OpenApiParameter(
                name="is_filterable",
                location=OpenApiParameter.QUERY,
                required=False,
                type=bool,
                description="Filter by filterable status",
            ),
            OpenApiParameter(
                name="is_searchable",
                location=OpenApiParameter.QUERY,
                required=False,
                type=bool,
                description="Filter by searchable status",
            ),
            OpenApiParameter(
                name="is_visible",
                location=OpenApiParameter.QUERY,
                required=False,
                type=bool,
                description="Filter by visible status",
            ),
            OpenApiParameter(
                name="include_system",
                location=OpenApiParameter.QUERY,
                required=False,
                type=bool,
                description="Include system features (only with channel context)",
            ),
            OpenApiParameter(
                name="exclude_feature_set",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Exclude features already assigned to this FeatureSet idx",
            ),
            OpenApiParameter(
                name="ordering",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Order results by field (e.g., 'display_order', '-idx')",
            ),
        ],
        responses={200: FeatureListResponse},
    )
    def list(self, request: Request, channel_idx: str | None = None) -> Response:
        """List features with filtering and pagination."""
        try:
            search = request.query_params.get("search", None)
            scope_param = request.query_params.get("scope", None)
            feature_type_param = request.query_params.get("feature_type", None)
            is_filterable_param = request.query_params.get("is_filterable", None)
            is_searchable_param = request.query_params.get("is_searchable", None)
            is_visible_param = request.query_params.get("is_visible", None)
            include_system_param = request.query_params.get("include_system", None)
            exclude_feature_set = request.query_params.get("exclude_feature_set", None)
            ordering = request.query_params.get("ordering", None)

            scope = None
            if scope_param is not None:
                try:
                    scope = int(scope_param)
                except ValueError:
                    return Response(
                        {"detail": "Invalid scope parameter: must be an integer"}, status=status.HTTP_400_BAD_REQUEST
                    )

            feature_type = None
            if feature_type_param is not None:
                try:
                    feature_type = int(feature_type_param)
                except ValueError:
                    return Response(
                        {"detail": "Invalid feature_type parameter: must be an integer"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            is_filterable = None
            if is_filterable_param is not None:
                is_filterable = is_filterable_param.lower() in ("true", "1", "yes")

            is_searchable = None
            if is_searchable_param is not None:
                is_searchable = is_searchable_param.lower() in ("true", "1", "yes")

            is_visible = None
            if is_visible_param is not None:
                is_visible = is_visible_param.lower() in ("true", "1", "yes")

            include_system = None
            if include_system_param is not None:
                include_system = include_system_param.lower() in ("true", "1", "yes")

            kwargs = dict(
                channel_idx=channel_idx,
                search=search,
                scope=scope,
                feature_type=feature_type,
                is_filterable=is_filterable,
                is_searchable=is_searchable,
                is_visible=is_visible,
                ordering=ordering,
                exclude_feature_set=exclude_feature_set,
            )
            if include_system is not None:
                kwargs["include_system"] = include_system

            features_qs = list_features(**kwargs)

            paginator = AdminPageNumberPagination()
            paginated_features = paginator.paginate_queryset(features_qs, request)

            lang = get_channel_language(channel_idx)
            feature_responses = [build_feature_response(f, language=lang) for f in paginated_features]

            response_data = FeatureListResponse(
                count=features_qs.count(),
                next=paginator.get_next_link(),
                previous=paginator.get_previous_link(),
                results=feature_responses,
            )

            return Response(response_data.model_dump(), status=status.HTTP_200_OK)

        except ObjectDoesNotExist:
            return not_found_response("Feature not found")
        except ValueError as e:
            return Response({"detail": f"Invalid parameter: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Retrieve feature by idx",
        description="Get a single feature by its idx",
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=False,
                type=str,
                description="Channel identifier (optional, for access validation)",
            ),
            OpenApiParameter(
                name="idx", location=OpenApiParameter.PATH, required=True, type=str, description="Feature idx"
            ),
        ],
        responses={200: FeatureResponse},
    )
    def retrieve(self, request: Request, idx: str, channel_idx: str | None = None) -> Response:
        """Retrieve a single feature by idx."""
        try:
            feature = get_feature_by_idx(idx=idx, channel_idx=channel_idx)
            lang = get_channel_language(channel_idx)
            return Response(build_feature_response(feature, language=lang).model_dump(), status=status.HTTP_200_OK)
        except ObjectDoesNotExist:
            return not_found_response(f"Feature with idx '{idx}' not found")
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Create feature",
        description="Create a new feature with translations and configuration",
        request=CreateFeatureRequest,
        responses={201: FeatureResponse},
    )
    def create(self, request: Request) -> Response:
        """Create a new feature."""
        try:
            data = CreateFeatureRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            feature = create_feature(
                idx=data.idx,
                name_t9n=data.name_t9n,
                desc=data.desc,
                scope=data.scope,
                feature_type=data.feature_type,
                frontend_input_type=data.frontend_input_type,
                filter_type=data.filter_type,
                display_order=data.display_order,
                is_required=data.is_required,
                is_visible=data.is_visible,
                is_filterable=data.is_filterable,
                is_searchable=data.is_searchable,
                is_comparable=data.is_comparable,
                is_for_customization=data.is_for_customization,
                exclude_from_inheritance=data.exclude_from_inheritance,
                has_visual_asset=data.has_visual_asset,
                is_seo=data.is_seo,
            )
            return Response(build_feature_response(feature).model_dump(), status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Update feature",
        description="Partially update an existing feature by idx. Only provided fields are updated.",
        parameters=[
            OpenApiParameter(
                name="idx", location=OpenApiParameter.PATH, required=True, type=str, description="Feature idx"
            )
        ],
        request=UpdateFeatureRequest,
        responses={200: FeatureResponse},
    )
    def partial_update(self, request: Request, idx: str, **kwargs: object) -> Response:
        """Partially update a feature by idx."""
        try:
            data = UpdateFeatureRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            fields = {k: v for k, v in data.model_dump().items() if v is not None}
            feature = update_feature(idx=idx, **fields)
            return Response(build_feature_response(feature).model_dump(), status=status.HTTP_200_OK)
        except ObjectDoesNotExist:
            return not_found_response(f"Feature '{idx}' not found")
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Delete feature",
        description="Delete a feature by idx. Returns counts of all deleted related objects.",
        parameters=[
            OpenApiParameter(
                name="idx", location=OpenApiParameter.PATH, required=True, type=str, description="Feature idx"
            )
        ],
        responses={200: {"description": "Deleted object counts"}},
    )
    def destroy(self, request: Request, idx: str, **kwargs: object) -> Response:
        """Delete a feature by idx."""
        try:
            deleted = delete_feature(idx=idx)
            return Response({"deleted": deleted}, status=status.HTTP_200_OK)
        except ObjectDoesNotExist:
            return not_found_response(f"Feature '{idx}' not found")
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="List attributes for feature",
        description="Get all attributes associated with a specific feature",
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=False,
                type=str,
                description="Channel identifier (optional)",
            ),
            OpenApiParameter(
                name="idx", location=OpenApiParameter.PATH, required=True, type=str, description="Feature idx"
            ),
        ],
        responses={200: AttributeListResponse},
    )
    @action(detail=True, methods=["get"], url_path="attributes")
    def attributes(self, request: Request, idx: str, channel_idx: str | None = None) -> Response:
        """List all attributes for a specific feature."""
        try:
            attributes_qs = list_attributes_for_feature(feature_idx=idx)
            lang = get_channel_language(channel_idx)

            paginator = AdminPageNumberPagination()
            paginated_attributes = paginator.paginate_queryset(attributes_qs, request)

            results = [
                AttributeResponse(
                    pk=attribute.pk,
                    feature_idx=attribute.feature.idx,
                    idx=attribute.idx,
                    name=resolve_attribute_name(attribute, language=lang),
                    name_t9n=attribute.name_t9n or {},
                    desc=attribute.desc,
                    group_idx=attribute.group.idx if attribute.group else None,
                    display_order=attribute.display_order,
                )
                for attribute in paginated_attributes
            ]

            response_data = AttributeListResponse(
                count=attributes_qs.count(),
                next=paginator.get_next_link(),
                previous=paginator.get_previous_link(),
                results=results,
            )

            return Response(response_data.model_dump(), status=status.HTTP_200_OK)

        except ObjectDoesNotExist:
            return not_found_response(f"Feature with idx '{idx}' not found")
        except Exception as e:
            return internal_error(e)

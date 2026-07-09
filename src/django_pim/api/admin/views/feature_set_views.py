# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Admin API views for feature sets.

DRF ViewSet for administrative feature set CRUD operations,
including bulk management of features within a set.
"""

from django_utils.api.v2_errors import raise_pydantic_as_drf
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from pydantic import ValidationError
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from ....models import AttributesGroup, Feature, FeatureInFeatureSet, FeatureSet
from ....schemas import (
    FeatureInSetResponse,
    FeatureSetListResponse,
    FeatureSetResponse,
    FeaturesInSetListResponse,
)
from ....schemas.requests import (
    BulkAddFeaturesRequest,
    BulkRemoveFeaturesRequest,
    CreateFeatureSetRequest,
    ReorderFeaturesInSetRequest,
    UpdateFeatureSetRequest,
)
from ....services import (
    build_feature_response,
    bulk_add_features_to_set,
    bulk_remove_features_from_set,
    create_feature_set,
    delete_feature_set,
    get_channel_language,
    get_feature_set_by_idx,
    list_feature_sets,
    list_features_in_feature_set,
    reorder_features_in_set,
    resolve_attributes_group_name,
    update_feature_set,
)
from ..errors import internal_error
from ..pagination import AdminPageNumberPagination
from ..permissions import IsAdminUser


def _build_feature_set_response(feature_set: FeatureSet) -> FeatureSetResponse:
    return FeatureSetResponse(
        pk=feature_set.pk,
        idx=feature_set.idx,
        name=feature_set.name,
        desc=feature_set.desc,
        is_default=feature_set.is_default,
        feature_count=feature_set.feature_count,
    )


@extend_schema_view(
    list=extend_schema(tags=["Feature Sets"]),
    retrieve=extend_schema(tags=["Feature Sets"]),
    create=extend_schema(tags=["Feature Sets"]),
    partial_update=extend_schema(tags=["Feature Sets"]),
    destroy=extend_schema(tags=["Feature Sets"]),
)
class FeatureSetViewSet(viewsets.ViewSet):
    """
    ViewSet for feature set management operations.

    Provides CRUD and nested feature management endpoints for feature sets.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="List feature sets",
        description="Get a paginated list of feature sets with feature counts",
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=False,
                type=str,
                description="Channel identifier (optional, for validation)",
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
                description="Search feature sets by idx or name",
            ),
            OpenApiParameter(
                name="is_default",
                location=OpenApiParameter.QUERY,
                required=False,
                type=bool,
                description="Filter by default status",
            ),
            OpenApiParameter(
                name="ordering",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="Order results by field (e.g., 'idx', '-name')",
            ),
        ],
        responses={200: FeatureSetListResponse},
    )
    def list(self, request: Request, channel_idx: str | None = None) -> Response:
        """List feature sets with filtering and pagination."""
        try:
            search = request.query_params.get("search", None)
            is_default_param = request.query_params.get("is_default", None)
            ordering = request.query_params.get("ordering", None)

            is_default = None
            if is_default_param is not None:
                is_default = is_default_param.lower() in ("true", "1", "yes")

            feature_sets_qs = list_feature_sets(
                channel_idx=channel_idx, search=search, is_default=is_default, ordering=ordering
            )

            paginator = AdminPageNumberPagination()
            paginated_feature_sets = paginator.paginate_queryset(feature_sets_qs, request)

            feature_set_responses = [_build_feature_set_response(fs) for fs in paginated_feature_sets]

            response_data = FeatureSetListResponse(
                count=feature_sets_qs.count(),
                next=paginator.get_next_link(),
                previous=paginator.get_previous_link(),
                results=feature_set_responses,
            )

            return Response(response_data.model_dump(), status=status.HTTP_200_OK)

        except FeatureSet.DoesNotExist:
            return Response({"detail": "Feature set not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"detail": f"Invalid parameter: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Retrieve feature set by idx",
        description="Get a single feature set by its idx with feature count",
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=False,
                type=str,
                description="Channel identifier (optional, for validation)",
            ),
            OpenApiParameter(
                name="idx", location=OpenApiParameter.PATH, required=True, type=str, description="FeatureSet idx"
            ),
        ],
        responses={200: FeatureSetResponse},
    )
    def retrieve(self, request: Request, idx: str, channel_idx: str | None = None) -> Response:
        """Retrieve a single feature set by idx."""
        try:
            feature_set = get_feature_set_by_idx(idx=idx, channel_idx=channel_idx)
            return Response(_build_feature_set_response(feature_set).model_dump(), status=status.HTTP_200_OK)
        except FeatureSet.DoesNotExist:
            return Response({"detail": f"Feature set with idx '{idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Create feature set",
        description="Create a new feature set.",
        request=CreateFeatureSetRequest,
        responses={201: FeatureSetResponse},
    )
    def create(self, request: Request) -> Response:
        """Create a new feature set."""
        try:
            data = CreateFeatureSetRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            feature_set = create_feature_set(idx=data.idx, name=data.name, desc=data.desc, is_default=data.is_default)
            # Fetch with feature_count annotation for response
            feature_set = get_feature_set_by_idx(idx=feature_set.idx)
            return Response(_build_feature_set_response(feature_set).model_dump(), status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Update feature set",
        description="Partially update an existing feature set by idx. Only provided fields are updated.",
        parameters=[
            OpenApiParameter(
                name="idx", location=OpenApiParameter.PATH, required=True, type=str, description="FeatureSet idx"
            )
        ],
        request=UpdateFeatureSetRequest,
        responses={200: FeatureSetResponse},
    )
    def partial_update(self, request: Request, idx: str, **kwargs: object) -> Response:
        """Partially update a feature set by idx."""
        try:
            data = UpdateFeatureSetRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            fields = {k: v for k, v in data.model_dump().items() if v is not None}
            feature_set = update_feature_set(idx=idx, **fields)
            return Response(_build_feature_set_response(feature_set).model_dump(), status=status.HTTP_200_OK)
        except FeatureSet.DoesNotExist:
            return Response({"detail": f"Feature set '{idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Delete feature set",
        description="Delete a feature set by idx. Returns counts of all deleted related objects.",
        parameters=[
            OpenApiParameter(
                name="idx", location=OpenApiParameter.PATH, required=True, type=str, description="FeatureSet idx"
            )
        ],
        responses={200: {"description": "Deleted object counts"}},
    )
    def destroy(self, request: Request, idx: str, **kwargs: object) -> Response:
        """Delete a feature set by idx."""
        try:
            deleted = delete_feature_set(idx=idx)
            return Response({"deleted": deleted}, status=status.HTTP_200_OK)
        except FeatureSet.DoesNotExist:
            return Response({"detail": f"Feature set '{idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        tags=["Feature Sets"],
        summary="List features in feature set",
        description="Get paginated list of features within a feature set, ordered by position",
        parameters=[
            OpenApiParameter(
                name="channel_idx",
                location=OpenApiParameter.PATH,
                required=False,
                type=str,
                description="Channel identifier (optional, for validation)",
            ),
            OpenApiParameter(
                name="idx", location=OpenApiParameter.PATH, required=True, type=str, description="FeatureSet idx"
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
        ],
        responses={200: FeaturesInSetListResponse},
    )
    def features(self, request: Request, idx: str, channel_idx: str | None = None) -> Response:
        """List features within a feature set, ordered by position."""
        try:
            features_in_set_qs = list_features_in_feature_set(feature_set_idx=idx, channel_idx=channel_idx)

            lang = get_channel_language(channel_idx)
            paginator = AdminPageNumberPagination()
            paginated_features_in_set = paginator.paginate_queryset(features_in_set_qs, request)

            feature_in_set_responses = [
                FeatureInSetResponse(
                    position=fis.position,
                    attributes_group_idx=(fis.attributes_group.idx if fis.attributes_group else None),
                    attributes_group_name=(
                        resolve_attributes_group_name(fis.attributes_group) if fis.attributes_group else None
                    ),
                    feature=build_feature_response(fis.feature, language=lang),
                )
                for fis in paginated_features_in_set
            ]

            response_data = FeaturesInSetListResponse(
                count=features_in_set_qs.count(),
                next=paginator.get_next_link(),
                previous=paginator.get_previous_link(),
                results=feature_in_set_responses,
            )

            return Response(response_data.model_dump(), status=status.HTTP_200_OK)

        except FeatureSet.DoesNotExist:
            return Response({"detail": f"Feature set with idx '{idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        tags=["Feature Sets"],
        summary="Add features to feature set",
        description="Bulk-add features to a feature set. Features already present are ignored (idempotent).",
        parameters=[
            OpenApiParameter(
                name="idx", location=OpenApiParameter.PATH, required=True, type=str, description="FeatureSet idx"
            )
        ],
        request=BulkAddFeaturesRequest,
        responses={201: {"description": "List of added FeatureInSetResponse entries"}},
    )
    def add_features(self, request: Request, idx: str, **kwargs: object) -> Response:
        """Bulk-add features to a feature set."""
        try:
            data = BulkAddFeaturesRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            entries = [
                {"feature_idx": f.feature_idx, "position": f.position, "attributes_group_idx": f.attributes_group_idx}
                for f in data.features
            ]
            results = bulk_add_features_to_set(feature_set_idx=idx, features=entries)
            lang = None

            response_items = [
                FeatureInSetResponse(
                    position=fis.position,
                    attributes_group_idx=(fis.attributes_group.idx if fis.attributes_group else None),
                    attributes_group_name=(
                        resolve_attributes_group_name(fis.attributes_group) if fis.attributes_group else None
                    ),
                    feature=build_feature_response(fis.feature, language=lang),
                )
                for fis in results
            ]

            return Response([item.model_dump() for item in response_items], status=status.HTTP_201_CREATED)

        except FeatureSet.DoesNotExist:
            return Response({"detail": f"Feature set '{idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Feature.DoesNotExist:
            return Response({"detail": "Feature not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        tags=["Feature Sets"],
        summary="Remove features from feature set",
        description="Bulk-remove features from a feature set. Features not present are ignored (idempotent).",
        parameters=[
            OpenApiParameter(
                name="idx", location=OpenApiParameter.PATH, required=True, type=str, description="FeatureSet idx"
            )
        ],
        request=BulkRemoveFeaturesRequest,
        responses={200: {"description": "Count of removed feature entries"}},
    )
    def remove_features(self, request: Request, idx: str, **kwargs: object) -> Response:
        """Bulk-remove features from a feature set."""
        try:
            data = BulkRemoveFeaturesRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            count = bulk_remove_features_from_set(feature_set_idx=idx, feature_idxs=data.feature_idxs)
            return Response({"removed": count}, status=status.HTTP_200_OK)
        except FeatureSet.DoesNotExist:
            return Response({"detail": f"Feature set '{idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        tags=["Feature Sets"],
        summary="Reorder features in feature set",
        description="Batch update positions and group assignments for features within a set",
        parameters=[
            OpenApiParameter(
                name="idx", location=OpenApiParameter.PATH, required=True, type=str, description="FeatureSet idx"
            )
        ],
        request=ReorderFeaturesInSetRequest,
        responses={200: {"description": "Number of features reordered"}, 400: {"description": "Validation error"}},
    )
    def reorder_features(self, request: Request, idx: str, **kwargs: object) -> Response:
        """Batch reorder features within a feature set."""
        try:
            data = ReorderFeaturesInSetRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            entries = [
                {"feature_idx": f.feature_idx, "position": f.position, "attributes_group_idx": f.attributes_group_idx}
                for f in data.features
            ]
            count = reorder_features_in_set(feature_set_idx=idx, features=entries)
            return Response({"reordered": count}, status=status.HTTP_200_OK)
        except FeatureSet.DoesNotExist:
            return Response({"detail": f"Feature set '{idx}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except (Feature.DoesNotExist, FeatureInFeatureSet.DoesNotExist):
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        except AttributesGroup.DoesNotExist:
            return Response({"detail": "Attributes group not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

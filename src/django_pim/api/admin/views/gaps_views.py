# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Admin API views for the quality-gaps highlighter (etap-04).

Four thin ViewSets over the gap services:
- ``GapDefinitionViewSet`` — CRUD for rules (global, not channel-scoped).
- ``GapFindingViewSet`` — bulk findings for a page of products (channel-scoped read).
- ``GapExemptionViewSet`` — per-product rule mutes (channel-scoped, etap-13 gap-spawn).
- ``GapOpsViewSet`` — 'recompute now' trigger + the rules-changed-vs-recomputed status.

No ORM here — all access goes through ``services``. Admin-only (JWT + IsAdminUser).
"""

from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist
from django_utils.api.v2_errors import raise_pydantic_as_drf
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from pydantic import ValidationError
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from ....schemas import (
    CreateGapDefinitionRequest,
    CreateGapExemptionRequest,
    GapDefinitionListResponse,
    GapDefinitionResponse,
    GapExemptionListResponse,
    GapExemptionResponse,
    GapFindingResponse,
    GapFindingsBulkResponse,
    GapRecomputeResponse,
    GapSettingsResponse,
    GapStatusResponse,
    UpdateGapDefinitionRequest,
    UpdateGapSettingsRequest,
)
from ....services import (
    create_exemption,
    create_gap_definition,
    delete_exemption,
    delete_gap_definition,
    get_findings_for_products,
    get_gap_definition,
    get_gaps_settings,
    get_gaps_status,
    list_exemptions,
    list_gap_definitions,
    trigger_full_recompute,
    update_gap_definition,
    update_gaps_settings,
)
from ..errors import internal_error
from ..pagination import AdminPageNumberPagination
from ..permissions import IsAdminUser

_MAX_PRODUCT_IDS = 200


def _gap_definition_response(d) -> GapDefinitionResponse:
    """Build the response schema from a GapDefinition instance (datetimes → ISO strings)."""
    return GapDefinitionResponse(
        key=d.key,
        check_key=d.check_key,
        params=d.params or {},
        languages=d.languages,
        channels=d.channels,
        severity=d.severity,
        label_t9n=d.label_t9n or {},
        active=d.active,
        display_order=d.display_order,
        created_at=d.created_at.isoformat() if d.created_at else None,
        modified_at=d.modified_at.isoformat() if d.modified_at else None,
    )


@extend_schema_view(
    list=extend_schema(tags=["Quality Gaps"]),
    retrieve=extend_schema(tags=["Quality Gaps"]),
    create=extend_schema(tags=["Quality Gaps"]),
    partial_update=extend_schema(tags=["Quality Gaps"]),
    destroy=extend_schema(tags=["Quality Gaps"]),
)
class GapDefinitionViewSet(viewsets.ViewSet):
    """CRUD for gap definitions (quality rules). Global — not channel-scoped."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="List gap definitions",
        parameters=[
            OpenApiParameter(name="page", type=int, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="page_size", type=int, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(
                name="search", type=str, location=OpenApiParameter.QUERY, required=False, description="Search by key"
            ),
            OpenApiParameter(name="is_active", type=bool, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(
                name="ordering",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="display_order|key|severity (+/-)",
            ),
        ],
        responses={200: GapDefinitionListResponse},
    )
    def list(self, request: Request) -> Response:
        try:
            search = request.query_params.get("search", None)
            ordering = request.query_params.get("ordering", None)
            is_active_param = request.query_params.get("is_active", None)
            is_active = None if is_active_param is None else is_active_param.lower() in ("true", "1", "yes")

            definitions_qs = list_gap_definitions(search=search, active=is_active, ordering=ordering)

            paginator = AdminPageNumberPagination()
            page = paginator.paginate_queryset(definitions_qs, request)
            results = [_gap_definition_response(d) for d in page]

            response_data = GapDefinitionListResponse(
                count=paginator.page.paginator.count,
                next=paginator.get_next_link(),
                previous=paginator.get_previous_link(),
                results=results,
            )
            return Response(response_data.model_dump(), status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(summary="Retrieve a gap definition", responses={200: GapDefinitionResponse})
    def retrieve(self, request: Request, key: str) -> Response:
        try:
            definition = get_gap_definition(key)
            return Response(_gap_definition_response(definition).model_dump(), status=status.HTTP_200_OK)
        except ObjectDoesNotExist:
            return Response({"detail": f"Gap definition '{key}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Create a gap definition", request=CreateGapDefinitionRequest, responses={201: GapDefinitionResponse}
    )
    def create(self, request: Request) -> Response:
        try:
            data = CreateGapDefinitionRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            definition = create_gap_definition(
                key=data.key,
                check_key=data.check_key,
                params=data.params,
                languages=data.languages,
                channels=data.channels,
                severity=data.severity,
                label_t9n=data.label_t9n,
                active=data.active,
                display_order=data.display_order,
            )
            return Response(_gap_definition_response(definition).model_dump(), status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Update a gap definition", request=UpdateGapDefinitionRequest, responses={200: GapDefinitionResponse}
    )
    def partial_update(self, request: Request, key: str) -> Response:
        try:
            data = UpdateGapDefinitionRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            definition = update_gap_definition(key, data.model_dump(exclude_unset=True))
            return Response(_gap_definition_response(definition).model_dump(), status=status.HTTP_200_OK)
        except ObjectDoesNotExist:
            return Response({"detail": f"Gap definition '{key}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(summary="Delete a gap definition", responses={200: None})
    def destroy(self, request: Request, key: str) -> Response:
        try:
            delete_gap_definition(key)
            return Response({"detail": f"Gap definition '{key}' deleted"}, status=status.HTTP_200_OK)
        except ObjectDoesNotExist:
            return Response({"detail": f"Gap definition '{key}' not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)


class GapFindingViewSet(viewsets.ViewSet):
    """Bulk findings for a page of products in one channel (CMS joins with the product list)."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Bulk gap findings for a page of products",
        parameters=[
            OpenApiParameter(name="channel_idx", type=str, location=OpenApiParameter.PATH, required=True),
            OpenApiParameter(
                name="product_ids",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Comma-separated product PKs",
            ),
            OpenApiParameter(name="language", type=str, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(
                name="severity",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="critical|warning",
            ),
            OpenApiParameter(
                name="only_source",
                type=bool,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Skip inherited",
            ),
        ],
        responses={200: GapFindingsBulkResponse},
    )
    def list(self, request: Request, channel_idx: str) -> Response:
        try:
            product_ids = self._parse_product_ids(request.query_params.get("product_ids"))
            language = request.query_params.get("language", None)
            severity = request.query_params.get("severity", None)
            only_source_param = request.query_params.get("only_source", None)
            only_source = bool(only_source_param) and only_source_param.lower() in ("true", "1", "yes")

            grouped = get_findings_for_products(
                channel_idx=channel_idx,
                product_ids=product_ids,
                language=language,
                severity=severity,
                only_source=only_source,
            )

            results = {
                str(pk): [
                    GapFindingResponse(
                        definition_key=f.definition.key,
                        label_t9n=f.definition.label_t9n or {},
                        severity=f.severity,
                        language=f.language,
                        inherited=f.inherited,
                        source_channel=f.source_channel,
                    )
                    for f in findings
                ]
                for pk, findings in grouped.items()
            }
            return Response(GapFindingsBulkResponse(results=results).model_dump(), status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @staticmethod
    def _parse_product_ids(raw: str | None) -> list[int]:
        if not raw:
            raise ValueError("product_ids is required")
        try:
            ids = [int(part) for part in raw.split(",") if part.strip()]
        except ValueError:
            raise ValueError("product_ids must be a comma-separated list of integers") from None
        if not ids:
            raise ValueError("product_ids is required")
        if len(ids) > _MAX_PRODUCT_IDS:
            raise ValueError(f"product_ids accepts at most {_MAX_PRODUCT_IDS} ids per call")
        return ids


def _gap_exemption_response(e) -> GapExemptionResponse:
    return GapExemptionResponse(
        id=e.pk,
        sku=e.product.real_product.sku,
        definition_key=e.definition.key,
        language=e.language,
        reason=e.reason,
        created_by_id=e.created_by_id,
        created_at=e.created_at.isoformat() if e.created_at else None,
    )


class GapExemptionViewSet(viewsets.ViewSet):
    """Per-product rule mutes (deep mute). Channel-scoped — products are addressed by (channel, sku)."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="List a product's gap exemptions",
        parameters=[
            OpenApiParameter(name="channel_idx", type=str, location=OpenApiParameter.PATH, required=True),
            OpenApiParameter(name="sku", type=str, location=OpenApiParameter.QUERY, required=True),
        ],
        responses={200: GapExemptionListResponse},
        tags=["Quality Gaps"],
    )
    def list(self, request: Request, channel_idx: str) -> Response:
        try:
            sku = request.query_params.get("sku")
            if not sku:
                raise ValueError("sku is required")
            exemptions = list_exemptions(channel_idx=channel_idx, sku=sku)
            payload = GapExemptionListResponse(results=[_gap_exemption_response(e) for e in exemptions])
            return Response(payload.model_dump(), status=status.HTTP_200_OK)
        except ObjectDoesNotExist as e:
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Mute a quality rule for one product",
        request=CreateGapExemptionRequest,
        responses={201: GapExemptionResponse},
        tags=["Quality Gaps"],
    )
    def create(self, request: Request, channel_idx: str) -> Response:
        try:
            data = CreateGapExemptionRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            exemption = create_exemption(
                channel_idx=channel_idx,
                sku=data.sku,
                definition_key=data.definition_key,
                language=data.language,
                reason=data.reason,
                created_by=request.user if request.user.is_authenticated else None,
            )
            return Response(_gap_exemption_response(exemption).model_dump(), status=status.HTTP_201_CREATED)
        except ObjectDoesNotExist as e:
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return internal_error(e)

    @extend_schema(summary="Unmute (delete an exemption)", responses={200: None}, tags=["Quality Gaps"])
    def destroy(self, request: Request, channel_idx: str, pk: int) -> Response:
        try:
            delete_exemption(channel_idx=channel_idx, exemption_id=pk)
            return Response({"detail": f"Gap exemption {pk} deleted"}, status=status.HTTP_200_OK)
        except ObjectDoesNotExist as e:
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return internal_error(e)


class GapOpsViewSet(viewsets.ViewSet):
    """Recompute trigger + rules-changed-vs-recomputed status. Global."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    @extend_schema(summary="Trigger a full recompute now", request=None, responses={202: GapRecomputeResponse})
    def recompute(self, request: Request) -> Response:
        try:
            result = trigger_full_recompute()
            running = result.get("status") in ("started", "already_running")
            payload = GapRecomputeResponse(status=result["status"], running=running)
            return Response(payload.model_dump(), status=status.HTTP_202_ACCEPTED)
        except Exception as e:
            return internal_error(e)

    @extend_schema(summary="Quality recompute status", responses={200: GapStatusResponse})
    def status(self, request: Request) -> Response:
        try:
            return Response(GapStatusResponse(**get_gaps_status()).model_dump(), status=status.HTTP_200_OK)
        except Exception as e:
            return internal_error(e)

    @extend_schema(summary="Quality gaps settings", responses={200: GapSettingsResponse})
    def get_settings(self, request: Request) -> Response:
        try:
            return Response(GapSettingsResponse(**get_gaps_settings()).model_dump(), status=status.HTTP_200_OK)
        except Exception as e:
            return internal_error(e)

    @extend_schema(
        summary="Update quality gaps settings",
        request=UpdateGapSettingsRequest,
        responses={200: GapSettingsResponse},
    )
    def patch_settings(self, request: Request) -> Response:
        try:
            data = UpdateGapSettingsRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)
        try:
            result = update_gaps_settings(gaps_skip_default_featureset=data.gaps_skip_default_featureset)
            return Response(GapSettingsResponse(**result).model_dump(), status=status.HTTP_200_OK)
        except Exception as e:
            return internal_error(e)

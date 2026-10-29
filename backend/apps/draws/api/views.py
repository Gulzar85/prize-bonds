"""Anonymous, read-only public API over *published* draw data.

Every response carries a disclaimer, an ``ETag`` and ``Cache-Control: public, max-age=300``. Nothing here can write.
"""

import hashlib
from typing import Any

from django.db.models import F, Min, OuterRef, Prefetch, Q, QuerySet, Subquery
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema, extend_schema_view, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.draws.api.serializers import (
    CheckRequestSerializer,
    DenominationSerializer,
    DrawDetailSerializer,
    DrawSummarySerializer,
    PublicNumberSerializer,
    WinSerializer,
)
from apps.draws.models import Denomination, Draw, DrawRevision, PrizeTier, WinningNumber

DISCLAIMER = (
    "Unofficial data compiled from files published by the Central Directorate of National Savings. It may contain "
    "errors or omissions. Always verify a win with National Savings (savings.gov.pk) before claiming any prize."
)
CACHE_SECONDS = 300
CACHE_CONTROL = f"public, max-age={CACHE_SECONDS}"


class PublicThrottle(AnonRateThrottle):
    scope = "public"


class CheckThrottle(AnonRateThrottle):
    scope = "public_check"


class PublicCursorPagination(CursorPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
    ordering = "-draw_date"

    def get_paginated_response(self, data: Any) -> Response:
        response = super().get_paginated_response(data)
        response.data["disclaimer"] = DISCLAIMER
        return response

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        wrapped = super().get_paginated_response_schema(schema)
        wrapped["properties"]["disclaimer"] = {"type": "string", "example": DISCLAIMER}
        return wrapped


class NumbersPagination(PublicCursorPagination):
    page_size = 100
    max_page_size = 500
    ordering = "number"


class PublicView(APIView):
    """Anonymous, throttled, cacheable. Subclasses set ``throttle_classes`` when they need a tighter limit."""

    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]
    throttle_classes = [PublicThrottle]

    def finalize_response(self, request: Request, response: Response, *args: Any, **kwargs: Any) -> Response:
        response = super().finalize_response(request, response, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            if isinstance(response.data, dict):
                response.data.setdefault("disclaimer", DISCLAIMER)
            response["Cache-Control"] = CACHE_CONTROL
            response.add_post_render_callback(_conditional_etag(request))
        return response


def _conditional_etag(request: Request) -> Any:
    def callback(response: HttpResponse) -> None:
        etag = '"' + hashlib.sha256(response.content).hexdigest()[:32] + '"'
        response["ETag"] = etag
        sent = request.META.get("HTTP_IF_NONE_MATCH", "")
        if request.method == "GET" and etag in [part.strip().removeprefix("W/") for part in sent.split(",")]:
            response.status_code = status.HTTP_304_NOT_MODIFIED
            response.content = b""

    return callback


def published_draws() -> QuerySet[Draw]:
    """The only draws the public API may ever show: those with an approved, published revision."""
    return Draw.objects.filter(status=Draw.Status.PUBLISHED, published_revision__isnull=False)


# --- views ------------------------------------------------------------------------------------------------------------


@extend_schema(
    summary="List denominations",
    responses=inline_serializer(
        "DenominationList",
        {"results": DenominationSerializer(many=True), "disclaimer": serializers.CharField()},
    ),
    examples=[
        OpenApiExample(
            "Denominations",
            value={
                "results": [
                    {
                        "slug": "rs-200",
                        "value_pkr": 200,
                        "kind": "REGULAR",
                        "name_en": "Rs 200 Prize Bond",
                        "name_ur": "200 روپے پرائز بانڈ",
                        "number_length": 6,
                    }
                ],
                "disclaimer": DISCLAIMER,
            },
            response_only=True,
        )
    ],
    tags=["public"],
)
class DenominationListView(PublicView):
    def get(self, request: Request) -> Response:
        queryset = Denomination.objects.filter(is_active=True)
        return Response({"results": DenominationSerializer(queryset, many=True).data})


DRAW_EXAMPLE = {
    "id": "0192f1c0-7b1e-7c3a-9d52-3f1c2a4b5d6e",
    "denomination": "rs-200",
    "denomination_value": 200,
    "draw_number": 107,
    "draw_date": "2026-09-15",
    "city": "Muzaffarabad",
    "revised": False,
}


@extend_schema_view(
    get=extend_schema(
        summary="List published draws",
        tags=["public"],
        parameters=[
            OpenApiParameter("denomination", OpenApiTypes.STR, description="Denomination slug, e.g. rs-200"),
            OpenApiParameter("year", OpenApiTypes.INT, description="Draw year, e.g. 2026"),
        ],
        examples=[
            OpenApiExample(
                "Page of draws",
                value=DRAW_EXAMPLE,
                response_only=True,
            )
        ],
    )
)
class DrawListView(PublicView, generics.ListAPIView[Draw]):
    serializer_class = DrawSummarySerializer
    pagination_class = PublicCursorPagination
    queryset = Draw.objects.none()  # schema generation only

    def get_queryset(self) -> QuerySet[Draw]:
        queryset = published_draws().select_related("denomination", "published_revision")
        params = self.request.query_params
        if slug := params.get("denomination"):
            queryset = queryset.filter(denomination__slug=slug)
        if year := params.get("year"):
            if not year.isdigit() or not (1990 <= int(year) <= 2100):
                raise ValidationError({"year": "Must be a four-digit year."})
            queryset = queryset.filter(draw_date__year=int(year))
        return queryset


@extend_schema(
    summary="Get one published draw",
    description="Header, prize tiers, the first and second prize numbers, published/revised dates and the source URL.",
    tags=["public"],
    responses=DrawDetailSerializer,
    examples=[
        OpenApiExample(
            "Draw",
            value={
                **DRAW_EXAMPLE,
                "published_at": "2026-09-15T14:30:00Z",
                "revised_at": None,
                "source_url": "https://savings.gov.pk/wp-content/uploads/2026/09/200_150926.txt",
                "tiers": [
                    {"rank": 1, "amount_pkr": 750000, "count": 1, "numbers": ["516806"]},
                    {
                        "rank": 2,
                        "amount_pkr": 250000,
                        "count": 5,
                        "numbers": ["381066", "425087", "796229", "799273", "844138"],
                    },
                    {"rank": 3, "amount_pkr": 1250, "count": 2394, "numbers": None},
                ],
                "disclaimer": DISCLAIMER,
            },
            response_only=True,
        )
    ],
)
class DrawDetailView(PublicView, generics.RetrieveAPIView[Draw]):
    serializer_class = DrawDetailSerializer
    lookup_field = "pk"
    queryset = Draw.objects.none()  # schema generation only

    def get_queryset(self) -> QuerySet[Draw]:
        first_published = (
            DrawRevision.objects.filter(
                draw=OuterRef("pk"), status__in=[DrawRevision.Status.APPROVED, DrawRevision.Status.SUPERSEDED]
            )
            .order_by()
            .values("draw")
            .annotate(first=Min("reviewed_at"))
            .values("first")
        )
        tiers = Prefetch(
            "published_revision__tiers",
            queryset=PrizeTier.objects.order_by("rank").prefetch_related("numbers"),
            to_attr="published_tiers",
        )
        return (
            published_draws()
            .select_related("denomination", "published_revision")
            .annotate(first_published_at=Subquery(first_published))
            .prefetch_related(tiers)
        )

    def get_object(self) -> Draw:
        draw: Draw = super().get_object()
        revision = draw.published_revision
        assert revision is not None
        draw.published_at = getattr(draw, "first_published_at", None) or draw.published_at
        draw.revised_at = revision.reviewed_at if revision.revision_no > 1 else None  # type: ignore[attr-defined]
        draw.source_url = revision.source_url or None  # type: ignore[attr-defined]
        draw.published_tiers = revision.published_tiers  # type: ignore[attr-defined]
        return draw


@extend_schema_view(
    get=extend_schema(
        summary="List a draw's winning numbers",
        tags=["public"],
        parameters=[OpenApiParameter("tier", OpenApiTypes.INT, description="1, 2 or 3")],
        examples=[
            OpenApiExample(
                "Numbers",
                value={"number": "000133", "tier": 3},
                response_only=True,
            )
        ],
    )
)
class DrawNumbersView(PublicView, generics.ListAPIView[WinningNumber]):
    serializer_class = PublicNumberSerializer
    pagination_class = NumbersPagination
    queryset = WinningNumber.objects.none()  # schema generation only

    def get_queryset(self) -> QuerySet[WinningNumber]:
        draw = published_draws().filter(pk=self.kwargs["pk"]).only("published_revision_id").first()
        if draw is None:
            raise NotFound()
        queryset = WinningNumber.objects.filter(revision_id=draw.published_revision_id).select_related("tier")
        if (tier := self.request.query_params.get("tier")) is not None:
            if tier not in {"1", "2", "3"}:
                raise ValidationError({"tier": "Must be 1, 2 or 3."})
            queryset = queryset.filter(tier__rank=int(tier))
        return queryset


@extend_schema(
    summary="Check numbers against every published draw",
    description=(
        "Send up to 50 numbers and/or up to 5 ranges of at most 1,000 numbers each, all for one denomination. "
        "Returns every published win for those numbers across all draws."
    ),
    tags=["public"],
    request=CheckRequestSerializer,
    responses=inline_serializer(
        "CheckResponse",
        {
            "denomination": serializers.CharField(),
            "wins": WinSerializer(many=True),
            "disclaimer": serializers.CharField(),
        },
    ),
    examples=[
        OpenApiExample(
            "Numbers and a range",
            value={
                "denomination": "rs-200",
                "numbers": ["516806", "000001"],
                "ranges": [{"from": "123400", "to": "123499"}],
            },
            request_only=True,
        ),
        OpenApiExample(
            "A win",
            value={
                "denomination": "rs-200",
                "wins": [
                    {
                        "number": "516806",
                        "draw_id": "0192f1c0-7b1e-7c3a-9d52-3f1c2a4b5d6e",
                        "draw_number": 107,
                        "draw_date": "2026-09-15",
                        "tier": 1,
                        "amount_pkr": 750000,
                    }
                ],
                "disclaimer": DISCLAIMER,
            },
            response_only=True,
        ),
    ],
)
class CheckView(PublicView):
    throttle_classes = [CheckThrottle]

    def post(self, request: Request) -> Response:
        serializer = CheckRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        denomination: Denomination = data["denomination"]

        condition = Q()
        if data["numbers"]:
            condition |= Q(number__in=data["numbers"])
        for start, end in data["ranges"]:  # fixed-length zero-padded numbers: string order equals numeric order
            condition |= Q(number__gte=start, number__lte=end)

        wins = (
            WinningNumber.objects.filter(
                condition,
                denomination=denomination,
                draw__status=Draw.Status.PUBLISHED,
                draw__published_revision_id=F("revision_id"),
            )
            .select_related("draw", "tier")
            .order_by("-draw__draw_date", "number")
        )
        results = [
            {
                "number": w.number,
                "draw_id": w.draw_id,
                "draw_number": w.draw.draw_number,
                "draw_date": w.draw.draw_date,
                "tier": w.tier.rank,
                "amount_pkr": w.tier.amount_pkr,
            }
            for w in wins
        ]
        return Response({"denomination": denomination.slug, "wins": WinSerializer(results, many=True).data})

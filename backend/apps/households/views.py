from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.core.mixins import HouseholdScopedViewMixin
from apps.households import selectors, services
from apps.households.models import Household, Membership
from apps.households.serializers import (
    HouseholdSerializer,
    HouseholdUpdateSerializer,
    MemberSerializer,
)

HOUSEHOLD_EXAMPLE = {
    "id": "0192f1c0-7b1e-7c3a-9d52-3f1c2a4b5d6e",
    "name": "Ahmed's Household",
    "role": "OWNER",
    "created_at": "2026-10-24T09:00:00Z",
}


@extend_schema_view(
    get=extend_schema(
        summary="List my households",
        examples=[OpenApiExample("Household", value=HOUSEHOLD_EXAMPLE, response_only=True)],
    )
)
class HouseholdListView(generics.ListAPIView[Household]):
    permission_classes = [IsAuthenticated]
    serializer_class = HouseholdSerializer

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return selectors.households_for_user(self.request.user)  # type: ignore[arg-type]


@extend_schema_view(
    get=extend_schema(
        summary="Get a household",
        examples=[OpenApiExample("Household", value=HOUSEHOLD_EXAMPLE, response_only=True)],
    ),
    patch=extend_schema(
        summary="Rename a household (owner only)",
        request=HouseholdUpdateSerializer,
        responses=HouseholdSerializer,
        examples=[OpenApiExample("Rename", value={"name": "Family Vault"}, request_only=True)],
    ),
)
class HouseholdDetailView(HouseholdScopedViewMixin, generics.RetrieveUpdateAPIView[Household]):
    permission_classes = [IsAuthenticated]
    serializer_class = HouseholdSerializer
    http_method_names = ["get", "patch", "head", "options"]
    method_permissions = {
        **HouseholdScopedViewMixin.method_permissions,
        "PATCH": "households.change_household",
    }
    queryset = Household.objects.all()

    def get_serializer_class(self):  # type: ignore[no-untyped-def]
        if self.request.method == "PATCH":
            return HouseholdUpdateSerializer
        return HouseholdSerializer

    def get_object(self) -> Household:
        household = self.household
        household.role = self.membership.role  # type: ignore[attr-defined]
        return household

    def perform_update(self, serializer: HouseholdUpdateSerializer) -> None:  # type: ignore[override]
        services.rename_household(self.household, serializer.validated_data["name"])

    def update(self, request, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().update(request, *args, **kwargs)
        from rest_framework.response import Response

        return Response(HouseholdSerializer(self.get_object(), context=self.get_serializer_context()).data)


@extend_schema(summary="List household members")
class HouseholdMembersView(HouseholdScopedViewMixin, generics.ListAPIView[Membership]):
    permission_classes = [IsAuthenticated]
    serializer_class = MemberSerializer
    queryset = Membership.objects.all()

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return selectors.members_of(self.household)

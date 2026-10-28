from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied

from apps.households.models import Household, Membership


class HouseholdScopedViewMixin:
    """
    Mixin that resolves household from URL and scopes queryset to user's households.
    """

    def get_household(self):
        household_id = self.kwargs.get("household_pk") or self.kwargs.get("household_id")
        if not household_id:
            raise PermissionDenied("Household not specified")

        household = get_object_or_404(Household, id=household_id)
        # Check membership
        if not Membership.objects.filter(user=self.request.user, household=household).exists():
            from rest_framework.exceptions import NotFound

            raise NotFound("Not found.")
        return household

    def get_queryset(self):
        queryset = super().get_queryset()
        try:
            household = self.get_household()
            if hasattr(queryset.model, "household"):
                return queryset.filter(household=household)
        except Exception:
            pass
        return queryset.none()

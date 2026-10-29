from typing import Any, cast

from django.db import models
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.core.household_scoped import HouseholdScopedModel
from apps.households.models import Household, Membership
from apps.households.selectors import get_membership

DEFAULT_PERMISSIONS = {
    "GET": "households.view_household",
    "HEAD": "households.view_household",
    "OPTIONS": "households.view_household",
}


class HouseholdScopedViewMixin(APIView):
    """Resolve the household from ``/households/{household_id}/...`` and enforce tenancy.

    * Non-members (and unknown households) get 404, never 403, so existence never leaks.
    * Members lacking the method's permission get 403.
    * ``scope_queryset`` restricts household-owned models to the resolved household.

    Must precede the DRF generic view in the MRO.
    """

    household_url_kwarg = "household_id"
    #: Maps HTTP method -> django-rules permission; unmapped methods require ``change_household``.
    method_permissions: dict[str, str] = DEFAULT_PERMISSIONS
    fallback_permission = "households.change_household"

    _membership: Membership | None = None

    @property
    def membership(self) -> Membership:
        if self._membership is None:
            membership = get_membership(cast(User, self.request.user), self.kwargs.get(self.household_url_kwarg))
            if membership is None:
                raise NotFound()
            self._membership = membership
        return self._membership

    @property
    def household(self) -> Household:
        return self.membership.household

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        perm = self.method_permissions.get(request.method or "", self.fallback_permission)
        if not request.user.has_perm(perm, self.household):
            raise PermissionDenied()

    def scope_queryset(self, queryset: models.QuerySet[Any]) -> models.QuerySet[Any]:
        if issubclass(queryset.model, HouseholdScopedModel) or hasattr(queryset.model, "household"):
            return queryset.filter(household=self.household)
        return queryset

    def get_queryset(self) -> models.QuerySet[Any]:
        return self.scope_queryset(super().get_queryset())  # type: ignore[misc]

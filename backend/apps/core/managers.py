from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import models
from django.db.models import FETCH_PEERS

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.households.models import Household


class FetchPeersManager(models.Manager[Any]):
    """Project-wide default manager.

    Django 6.1 fetch modes: FETCH_PEERS loads a deferred field or related object
    for every instance fetched by the same query in one extra query, so lazy
    access inside a loop never turns into an N+1.
    """

    def get_queryset(self) -> models.QuerySet[Any]:
        return super().get_queryset().fetch_mode(FETCH_PEERS)


class SoftDeleteManager(FetchPeersManager):
    def get_queryset(self) -> models.QuerySet[Any]:
        return super().get_queryset().filter(deleted_at__isnull=True)


class HouseholdScopedManager(FetchPeersManager):
    def for_household(self, household: Household) -> models.QuerySet[Any]:
        return self.get_queryset().filter(household=household)

    def visible_to(self, user: User) -> models.QuerySet[Any]:
        return self.get_queryset().filter(
            household__memberships__user=user,
            household__deleted_at__isnull=True,
        )

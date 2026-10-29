import uuid

from django.db.models import OuterRef, QuerySet, Subquery

from apps.accounts.models import User
from apps.households.models import Household, Membership


def households_for_user(user: User) -> QuerySet[Household]:
    """Households the user belongs to, annotated with the user's role as `role`."""
    role = Membership.objects.filter(user=user, household=OuterRef("pk")).values("role")[:1]
    queryset: QuerySet[Household] = Household.objects.filter(memberships__user=user)
    return queryset.annotate(role=Subquery(role)).order_by("-created_at", "-id")


def get_membership(user: User, household_id: uuid.UUID | str) -> Membership | None:
    return (
        Membership.objects.select_related("household")
        .filter(user=user, household_id=household_id, household__deleted_at__isnull=True)
        .first()
    )


def members_of(household: Household) -> QuerySet[Membership]:
    return Membership.objects.filter(household=household).select_related("user")

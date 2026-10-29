from django.db import transaction

from apps.accounts.models import User
from apps.core.exceptions import DomainError
from apps.households.models import Household, Membership


class LastOwnerError(DomainError):
    code = "last_owner"
    detail = "A household must keep at least one owner."


def _owner_count_locked(household: Household) -> int:
    # Lock the household row so two concurrent demotions cannot both pass the check.
    Household.all_objects.select_for_update().get(pk=household.pk)
    return Membership.objects.filter(household=household, role=Membership.Role.OWNER).count()


@transaction.atomic
def create_personal_household(user: User) -> Household:
    """Idempotently create the user's personal household with the user as OWNER."""
    existing: Household | None = Household.objects.filter(created_by=user, memberships__user=user).first()
    if existing is not None:
        return existing
    household: Household = Household.objects.create(name=f"{user.full_name or user.email}'s Household", created_by=user)
    Membership.objects.create(user=user, household=household, role=Membership.Role.OWNER)
    return household


@transaction.atomic
def rename_household(household: Household, name: str) -> Household:
    household.name = name
    household.save(update_fields=["name", "updated_at"])
    return household


@transaction.atomic
def change_member_role(membership: Membership, role: str) -> Membership:
    if membership.role == Membership.Role.OWNER and role != Membership.Role.OWNER:
        if _owner_count_locked(membership.household) <= 1:
            raise LastOwnerError()
    membership.role = role
    membership.save(update_fields=["role", "updated_at"])
    return membership


@transaction.atomic
def remove_member(membership: Membership) -> None:
    if membership.role == Membership.Role.OWNER and _owner_count_locked(membership.household) <= 1:
        raise LastOwnerError()
    membership.delete()

import rules
from django.contrib.auth.models import AnonymousUser

from apps.accounts.models import User
from apps.households.models import Household, Membership


def _role_in(user: User | AnonymousUser, household: Household | None, roles: set[str]) -> bool:
    if household is None or not user.is_authenticated:
        return False
    return Membership.objects.filter(user=user, household=household, role__in=roles).exists()


@rules.predicate
def is_member(user: User, household: Household | None) -> bool:
    return _role_in(user, household, set(Membership.Role.values))


@rules.predicate
def is_owner(user: User, household: Household | None) -> bool:
    return _role_in(user, household, {Membership.Role.OWNER})


@rules.predicate
def is_editor_or_owner(user: User, household: Household | None) -> bool:
    return _role_in(user, household, {Membership.Role.OWNER, Membership.Role.EDITOR})


rules.add_perm("households.view_household", is_member)
rules.add_perm("households.change_household", is_owner)
rules.add_perm("households.manage_members", is_owner)

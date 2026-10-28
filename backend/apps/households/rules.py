import rules


@rules.predicate
def is_member(user, household):
    from apps.households.models import Membership

    return Membership.objects.filter(user=user, household=household).exists()


@rules.predicate
def is_owner(user, household):
    from apps.households.models import Membership

    return Membership.objects.filter(
        user=user, household=household, role=Membership.Role.OWNER
    ).exists()


@rules.predicate
def is_editor_or_owner(user, household):
    from apps.households.models import Membership

    return Membership.objects.filter(
        user=user,
        household=household,
        role__in=[Membership.Role.OWNER, Membership.Role.EDITOR],
    ).exists()


rules.add_perm("households.view_household", is_member)
rules.add_perm("households.change_household", is_owner)
rules.add_perm("households.manage_members", is_owner)

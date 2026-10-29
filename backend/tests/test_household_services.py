import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import User
from apps.households import services
from apps.households.models import Household, Membership
from apps.households.rules import is_editor_or_owner, is_member, is_owner
from tests.factories import HouseholdFactory, MembershipFactory, UserFactory

R = Membership.Role


@pytest.mark.django_db
def test_create_personal_household_is_idempotent():
    user = UserFactory()
    first = services.create_personal_household(user)
    second = services.create_personal_household(user)
    assert first == second
    assert Membership.objects.get(user=user, household=first).role == R.OWNER
    assert Household.objects.count() == 1


@pytest.mark.django_db
def test_last_owner_cannot_be_demoted_or_removed():
    household = HouseholdFactory()
    owner = MembershipFactory(household=household, role=R.OWNER)
    with pytest.raises(services.LastOwnerError):
        services.change_member_role(owner, R.EDITOR)
    with pytest.raises(services.LastOwnerError):
        services.remove_member(owner)


@pytest.mark.django_db
def test_owner_can_be_demoted_or_removed_when_another_exists():
    household = HouseholdFactory()
    a = MembershipFactory(household=household, role=R.OWNER)
    b = MembershipFactory(household=household, role=R.OWNER)
    services.change_member_role(a, R.EDITOR)
    assert Membership.objects.get(pk=a.pk).role == R.EDITOR
    with pytest.raises(services.LastOwnerError):
        services.remove_member(b)
    services.change_member_role(a, R.OWNER)
    services.remove_member(b)
    assert not Membership.objects.filter(pk=b.pk).exists()


@pytest.mark.django_db
def test_predicates():
    household = HouseholdFactory()
    owner = MembershipFactory(household=household, role=R.OWNER).user
    editor = MembershipFactory(household=household, role=R.EDITOR).user
    viewer = MembershipFactory(household=household, role=R.VIEWER).user
    stranger = UserFactory()
    users = (owner, editor, viewer, stranger)
    assert [is_member(u, household) for u in users] == [True, True, True, False]
    assert [is_owner(u, household) for u in users] == [True, False, False, False]
    assert [is_editor_or_owner(u, household) for u in users] == [True, True, False, False]
    assert owner.has_perm("households.change_household", household)
    assert not editor.has_perm("households.manage_members", household)
    assert viewer.has_perm("households.view_household", household)
    assert not is_member(owner, None)


@pytest.mark.django_db
def test_db_cascade_removes_memberships():
    household = HouseholdFactory()
    membership = MembershipFactory(household=household)
    Household.all_objects.filter(pk=household.pk).delete()
    assert not Membership.objects.filter(pk=membership.pk).exists()


@pytest.mark.django_db
def test_user_email_is_case_insensitively_unique():
    User.objects.create_user("Dup@Example.com", "pw-Str0ng!xyz")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("dup@example.com", "pw-Str0ng!xyz")

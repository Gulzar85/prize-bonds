import pytest
from rest_framework.test import APIClient

from tests.factories import HouseholdFactory, MembershipFactory, UserFactory


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def authenticated_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def household(user):
    household = HouseholdFactory(created_by=user)
    MembershipFactory(user=user, household=household, role="OWNER")
    return household


@pytest.fixture
def other_user():
    return UserFactory()


@pytest.fixture
def other_household(other_user):
    household = HouseholdFactory(created_by=other_user)
    MembershipFactory(user=other_user, household=household, role="OWNER")
    return household

import pytest
from allauth.headless.tokens.strategies.jwt import internal  # noqa: F401
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.households.models import Membership
from tests.factories import HouseholdFactory, MembershipFactory, UserFactory


@pytest.fixture(autouse=True)
def _clear_cache():  # type: ignore[no-untyped-def]
    cache.clear()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def household():  # type: ignore[no-untyped-def]
    return HouseholdFactory()


@pytest.fixture
def other_household():  # type: ignore[no-untyped-def]
    return HouseholdFactory()


@pytest.fixture
def make_member(household):  # type: ignore[no-untyped-def]
    def _make(role: str = Membership.Role.OWNER, hh=None):  # type: ignore[no-untyped-def]
        user = UserFactory()
        MembershipFactory(user=user, household=hh or household, role=role)
        return user

    return _make


@pytest.fixture
def client_for():  # type: ignore[no-untyped-def]
    def _client(user) -> APIClient:  # type: ignore[no-untyped-def]
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    return _client

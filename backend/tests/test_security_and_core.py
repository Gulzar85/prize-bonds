import pytest
from allauth.mfa.models import Authenticator
from django.core.cache import cache
from django.test import Client, override_settings
from django.utils import timezone

from api.v1.throttles import parse_rate
from apps.core.exceptions import DomainError
from tests.factories import PASSWORD, HouseholdFactory, UserFactory

BACKEND = "django.contrib.auth.backends.ModelBackend"
LOGIN = "/api/v1/auth/app/v1/auth/login"


def test_parse_rate():
    assert parse_rate("5/minute") == (5, 60)


@override_settings(
    AUTH_THROTTLE_RATES={"login": "3/minute", "signup": "3/hour", "password_reset": "3/hour", "mfa": "3/minute"}
)
@pytest.mark.django_db
def test_login_is_throttled_per_ip():
    cache.clear()
    client = Client()
    codes = [
        client.post(LOGIN, {"email": "x@example.com", "password": "nope"}, content_type="application/json").status_code
        for _ in range(5)
    ]
    assert codes[:3] != [429, 429, 429]
    assert codes[3:] == [429, 429]
    last = client.post(LOGIN, {}, content_type="application/json")
    assert last["Content-Type"] == "application/problem+json"
    assert last["Retry-After"] == "60"


@override_settings(
    AUTH_THROTTLE_RATES={"login": "1/minute", "signup": "1/hour", "password_reset": "1/hour", "mfa": "1/minute"}
)
def test_other_endpoints_not_throttled_by_login_scope():
    cache.clear()
    client = Client()
    for _ in range(3):
        assert client.get("/health/live/").status_code == 200


@pytest.mark.django_db
def test_request_id_is_echoed_and_generated(client):
    assert client.get("/health/live/", headers={"X-Request-ID": "abc-123"})["X-Request-ID"] == "abc-123"
    assert client.get("/health/live/")["X-Request-ID"]


@pytest.mark.django_db
def test_unauthenticated_error_is_problem_json(client_for):
    response = client_for(None).get("/api/v1/me/")
    assert response.status_code == 401
    assert response["Content-Type"].startswith("application/problem+json")
    assert response.data["status"] == 401
    assert response.data["type"].endswith("/not_authenticated")
    assert response.data["request_id"]


@pytest.mark.django_db
def test_domain_error_maps_to_409(client_for, monkeypatch):
    from apps.households import views

    def boom(*args, **kwargs):
        raise DomainError()

    monkeypatch.setattr(views.services, "rename_household", boom)
    household = HouseholdFactory()
    from tests.factories import MembershipFactory

    owner = MembershipFactory(household=household).user
    response = client_for(owner).patch(f"/api/v1/households/{household.id}/", {"name": "x"}, format="json")
    assert response.status_code == 409
    assert response.data["type"].endswith("/domain_error")


@pytest.mark.django_db
def test_soft_delete_and_restore():
    household = HouseholdFactory()
    from apps.households.models import Household

    household.soft_delete()
    assert not Household.objects.filter(pk=household.pk).exists()
    assert Household.all_objects.filter(pk=household.pk).exists()
    household.restore()
    assert Household.objects.filter(pk=household.pk).exists()


@pytest.mark.django_db
def test_uuid7_primary_keys_are_time_ordered():
    first, second = UserFactory(), UserFactory()
    assert first.id.version == 7
    assert first.id < second.id


@pytest.mark.django_db
def test_user_manager_validation():
    from apps.accounts.models import User

    with pytest.raises(ValueError):
        User.objects.create_user("")
    with pytest.raises(ValueError):
        User.objects.create_superuser("a@example.com", PASSWORD, is_staff=False)
    admin = User.objects.create_superuser("Root@Example.com", PASSWORD)
    assert admin.is_staff
    assert admin.email == "root@example.com"
    assert str(admin) == "root@example.com"
    assert admin.get_short_name() == "root@example.com"


@pytest.mark.django_db
class TestAdminRequiresMfa:
    def _staff(self):
        user = UserFactory(is_staff=True, is_superuser=True)
        return user

    def test_anonymous_is_redirected_to_allauth_login(self, client):
        response = client.get("/admin/", follow=True)
        assert response.redirect_chain[-1][0].startswith("/accounts/login/")

    def test_staff_without_mfa_is_refused(self, client):
        client.force_login(self._staff(), backend=BACKEND)
        response = client.get("/admin/", follow=True)
        assert b"Site administration" not in response.content
        assert response.redirect_chain[0][0].startswith("/admin/login/")

    def test_staff_with_mfa_can_enter(self, client):
        user = self._staff()
        Authenticator.objects.create(user=user, type=Authenticator.Type.TOTP, data={"secret": "x"})
        client.force_login(user, backend=BACKEND)
        assert client.get("/admin/").status_code == 200

    def test_mfa_requirement_can_be_disabled_in_dev(self, client):
        user = self._staff()
        client.force_login(user, backend=BACKEND)
        with override_settings(ADMIN_REQUIRE_MFA=False):
            assert client.get("/admin/").status_code == 200

    def test_non_staff_never_enters(self, client):
        client.force_login(UserFactory(), backend=BACKEND)
        with override_settings(ADMIN_REQUIRE_MFA=False):
            assert client.get("/admin/").status_code != 200


@pytest.mark.django_db
def test_cursor_pagination_is_default(client_for):
    from tests.factories import MembershipFactory

    user = UserFactory()
    for _ in range(3):
        MembershipFactory(user=user)
    body = client_for(user).get("/api/v1/households/?page_size=2").json()
    assert len(body["results"]) == 2
    assert body["next"] and "cursor=" in body["next"]
    assert timezone.now()

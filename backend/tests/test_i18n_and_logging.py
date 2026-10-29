import pytest
import structlog
from django.core import mail
from rest_framework.test import APIClient

from tests.factories import UserFactory

BASE = "/api/v1/auth/app/v1"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "subject", "marker"),
    [("en", "Reset your password", "unofficial tool"), ("ur", "اپنا پاس ورڈ ری سیٹ کریں", "غیر سرکاری")],
)
def test_password_reset_email_uses_preferred_language(language, subject, marker):
    user = UserFactory(preferred_language=language)
    response = APIClient().post(f"{BASE}/auth/password/request", {"email": user.email}, format="json")
    assert response.status_code == 200
    message = mail.outbox[-1]
    assert subject in message.subject
    assert marker in message.body


@pytest.mark.django_db
def test_signup_email_is_confirmation_with_link():
    APIClient().post(f"{BASE}/auth/signup", {"email": "z@example.com", "password": "Str0ng-Passw0rd!x"}, format="json")
    message = mail.outbox[-1]
    assert "Confirm your email address" in message.subject
    assert "verify-email/" in message.body


@pytest.mark.django_db
def test_user_id_is_bound_to_log_context_for_jwt_requests(client_for):
    user = UserFactory()
    # force_authenticate bypasses the authentication class, so go through a real token.
    from allauth.headless.tokens.strategies.jwt import internal

    session = APIClient()
    session.post(f"{BASE}/auth/login", {"email": user.email, "password": "Str0ng-Passw0rd!x"}, format="json")
    token = session.post(
        f"{BASE}/auth/login", {"email": user.email, "password": "Str0ng-Passw0rd!x"}, format="json"
    ).json()["meta"]["access_token"]
    assert internal
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert client.get("/api/v1/me/").status_code == 200
    assert structlog.contextvars.get_contextvars()["user_id"] == str(user.pk)

import re
from urllib.parse import unquote

import pyotp
import pytest
from django.core import mail
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.households.models import Household, Membership
from tests.factories import PASSWORD

BASE = "/api/v1/auth/app/v1"
EMAIL = "new.user@example.com"


def _post(client, path, data=None, **extra):  # type: ignore[no-untyped-def]
    return client.post(f"{BASE}{path}", data or {}, format="json", **extra)


def _signup_and_verify(client: APIClient) -> None:
    response = _post(client, "/auth/signup", {"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 401  # email verification pending
    key = re.search(r"verify-email/([^\s/]+)", mail.outbox[-1].body).group(1)
    key = unquote(key)
    response = _post(client, "/auth/email/verify", {"key": key})
    assert response.status_code in (200, 401)


def _login(client):  # type: ignore[no-untyped-def]
    return _post(client, "/auth/login", {"email": EMAIL, "password": PASSWORD})


@pytest.mark.django_db
def test_signup_verify_login_refresh_logout():
    client = APIClient()
    _signup_and_verify(client)

    # Verification created exactly one personal household owned by the user.
    user = User.objects.get(email=EMAIL)
    assert Household.objects.filter(memberships__user=user).count() == 1
    assert Membership.objects.get(user=user).role == Membership.Role.OWNER

    response = _login(client)
    assert response.status_code == 200, response.content
    meta = response.json()["meta"]
    access, refresh, session = meta["access_token"], meta["refresh_token"], meta["session_token"]

    # The access token authenticates DRF endpoints.
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    me = authed.get("/api/v1/me/")
    assert me.status_code == 200
    assert me.json()["email"] == EMAIL
    households = authed.get("/api/v1/households/").json()["results"]
    assert [h["role"] for h in households] == ["OWNER"]

    # Refresh rotates the refresh token.
    refreshed = _post(client, "/tokens/refresh", {"refresh_token": refresh})
    assert refreshed.status_code == 200
    data = refreshed.json()["data"]
    assert data["access_token"]
    assert data["refresh_token"] != refresh
    # The old refresh token is single-use.
    assert _post(client, "/tokens/refresh", {"refresh_token": refresh}).status_code == 400

    # Logout invalidates the session, so refresh is rejected afterwards.
    logout = client.delete(f"{BASE}/auth/session", HTTP_X_SESSION_TOKEN=session)
    assert logout.status_code == 401
    assert _post(client, "/tokens/refresh", {"refresh_token": data["refresh_token"]}).status_code == 400
    assert authed.get("/api/v1/me/").status_code == 401


@pytest.mark.django_db
def test_login_blocked_until_email_verified():
    client = APIClient()
    assert _post(client, "/auth/signup", {"email": EMAIL, "password": PASSWORD}).status_code == 401
    response = _login(client)
    assert response.status_code == 401
    assert "access_token" not in response.json().get("meta", {})


@pytest.mark.django_db
def test_me_patch_and_phone_validation():
    client = APIClient()
    _signup_and_verify(client)
    token = _login(client).json()["meta"]["access_token"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    ok = client.patch("/api/v1/me/", {"full_name": "Ahmed", "phone": "+923001234567"}, format="json")
    assert ok.status_code == 200
    assert ok.json()["full_name"] == "Ahmed"
    bad = client.patch("/api/v1/me/", {"phone": "0300"}, format="json")
    assert bad.status_code == 400
    immutable = client.patch("/api/v1/me/", {"email": "x@example.com"}, format="json")
    assert immutable.json()["email"] == EMAIL


@pytest.mark.django_db
def test_totp_mfa_login_and_single_use_recovery_code():
    client = APIClient()
    _signup_and_verify(client)
    session = _login(client).json()["meta"]["session_token"]
    headers = {"HTTP_X_SESSION_TOKEN": session}

    # Enroll TOTP (sensitive: requires reauthentication with the password).
    reauth = _post(client, "/auth/reauthenticate", {"password": PASSWORD}, **headers)
    assert reauth.status_code == 200, reauth.content
    pending = client.get(f"{BASE}/account/authenticators/totp", **headers)
    assert pending.status_code == 404
    secret = pending.json()["meta"]["secret"]
    code = pyotp.TOTP(secret).now()
    activated = client.post(f"{BASE}/account/authenticators/totp", {"code": code}, format="json", **headers)
    assert activated.status_code == 200, activated.content

    codes = client.get(f"{BASE}/account/authenticators/recovery-codes", **headers).json()["data"]["unused_codes"]
    assert len(codes) > 0

    cache.clear()  # allauth rejects re-use of the code that activated TOTP in the same window

    def second_factor(code: str):  # type: ignore[no-untyped-def]
        """Fresh login (password only) then the second factor, as an app client would."""
        fresh = APIClient()
        first = _login(fresh)
        assert first.status_code == 401
        assert any(f["id"] == "mfa_authenticate" for f in first.json()["data"]["flows"])
        token = first.json()["meta"]["session_token"]
        return _post(fresh, "/auth/2fa/authenticate", {"code": code}, HTTP_X_SESSION_TOKEN=token)

    done = second_factor(pyotp.TOTP(secret).now())
    assert done.status_code == 200, done.content
    assert done.json()["meta"]["access_token"]

    # Recovery code works once.
    assert second_factor(codes[0]).status_code == 200
    assert second_factor(codes[0]).status_code == 400

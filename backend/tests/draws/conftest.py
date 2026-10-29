import datetime
from pathlib import Path

import pytest
from allauth.mfa.models import Authenticator
from django.contrib.auth.models import Group

from apps.draws import alerts
from apps.draws.ingestion.fetcher import Fetched
from apps.draws.models import Denomination
from tests.factories import UserFactory

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "draws"


@pytest.fixture(autouse=True)
def raw_storage_in_tmp(settings, tmp_path):
    """Never write test downloads into the project's private_media directory."""
    settings.STORAGES = {
        **settings.STORAGES,
        "draws_raw": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path / "raw")},
        },
    }


@pytest.fixture
def sent_alerts(monkeypatch):
    """Capture alerts instead of emailing/logging them; each item is (code, message, context)."""
    captured: list[tuple[str, str, dict]] = []
    monkeypatch.setattr(alerts, "raise_alert", lambda code, message, **ctx: captured.append((code, message, ctx)))
    return captured


def make_operator(mfa: bool = True, **kwargs):
    user = UserFactory(**{"is_staff": True, **kwargs})  # operators work in the Django admin
    user.groups.add(Group.objects.get(name="data_operator"))
    if mfa:
        Authenticator.objects.create(user=user, type=Authenticator.Type.TOTP, data={"secret": "x"})
    return user


@pytest.fixture
def operator():
    return make_operator()


@pytest.fixture
def other_operator():
    return make_operator()


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def fetched(
    content: bytes, url: str = "https://savings.gov.pk/wp-content/uploads/x.txt", etag: str = '"e1"'
) -> Fetched:
    import hashlib

    return Fetched(
        url=url,
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        content_type="text/plain",
        etag=etag,
        last_modified="",
    )


class FakeFetcher:
    """Stands in for apps.draws.ingestion.fetcher.Fetcher; returns whatever it is given, in order."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def get_file(self, url, ext, etag="", last_modified=""):
        self.calls.append({"url": url, "ext": ext, "etag": etag, "last_modified": last_modified})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def rs200() -> Denomination:
    return Denomination.objects.get(slug="rs-200")


SEPT_15 = datetime.date(2026, 9, 15)

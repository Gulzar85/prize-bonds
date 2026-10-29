import pytest


@pytest.mark.django_db
def test_health_live(client):
    assert client.get("/health/live/").status_code == 200


@pytest.mark.django_db
def test_health_ready(client):
    assert client.get("/health/ready/").status_code == 200


@pytest.mark.django_db
def test_health_ready_fails_when_a_check_fails(client, monkeypatch):
    from health_check.checks import Database
    from health_check.exceptions import ServiceUnavailable

    async def boom(self):
        raise ServiceUnavailable("db down")

    monkeypatch.setattr(Database, "run", boom)
    assert client.get("/health/ready/").status_code == 500

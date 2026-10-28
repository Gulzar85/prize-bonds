import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_health_live(client):
    response = client.get("/health/live/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_health_ready(client):
    response = client.get("/health/ready/")
    assert response.status_code == 200

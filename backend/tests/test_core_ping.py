import pytest

from apps.core.tasks import ping


@pytest.mark.django_db
def test_ping_task():
    result = ping()
    assert result == "pong"

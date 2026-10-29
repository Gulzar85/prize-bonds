import pytest
import sentry_sdk
from django.core import mail

from apps.draws import alerts
from tests.draws.conftest import make_operator
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_operator_emails_are_the_active_data_operators_only():
    first = make_operator(email="b-ops@example.com")
    make_operator(email="a-ops@example.com")
    inactive = make_operator(email="gone@example.com")
    inactive.is_active = False
    inactive.save()
    UserFactory(email="nobody@example.com")  # not in the group
    assert alerts.operator_emails() == ["a-ops@example.com", first.email]


def test_an_alert_goes_to_sentry_and_emails_the_operators(monkeypatch):
    make_operator(email="ops@example.com")
    captured = []
    monkeypatch.setattr(sentry_sdk, "capture_message", lambda message, level=None: captured.append((message, level)))
    alerts.raise_alert(alerts.DRAW_NOT_FOUND, "The Rs 200 draw has not appeared", denomination="rs-200")
    assert captured == [("[draws] draw_not_found: The Rs 200 draw has not appeared", "warning")]
    [message] = mail.outbox
    assert message.to == ["ops@example.com"]
    assert message.subject == "[Prize Bond Tracker] draw_not_found"
    assert "denomination: rs-200" in message.body


def test_without_operators_nothing_is_emailed():
    alerts.raise_alert(alerts.PARSE_FAILURE, "could not parse")
    assert mail.outbox == []


def test_alert_delivery_failure_never_breaks_ingestion(monkeypatch, caplog):
    make_operator(email="ops@example.com")

    def boom(*args, **kwargs):
        raise OSError("smtp down")

    monkeypatch.setattr(alerts, "send_mail", boom)
    alerts.raise_alert(alerts.REVIEW_OVERDUE, "waiting")  # must not raise
    assert "could not deliver draws alert review_overdue" in caplog.text


@pytest.mark.parametrize(
    "code",
    [
        alerts.DRAW_NOT_FOUND,
        alerts.PARSE_FAILURE,
        alerts.UNKNOWN_DENOMINATION,
        alerts.UNKNOWN_LAYOUT,
        alerts.REVISION_DETECTED,
        alerts.REVIEW_OVERDUE,
        alerts.FETCH_FAILURE,
    ],
)
def test_every_alert_condition_has_a_stable_code_that_can_be_raised(code, monkeypatch):
    monkeypatch.setattr(sentry_sdk, "capture_message", lambda *a, **k: None)
    alerts.raise_alert(code, "x")
    assert alerts.logger.name == "draws.alerts"

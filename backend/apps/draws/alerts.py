"""Operational alerts: Sentry plus an email to the data operators. Each alert has a stable code."""

import logging
from typing import Any

import sentry_sdk
from django.contrib.auth import get_user_model
from django.core.mail import send_mail

from apps.draws.rules import DATA_OPERATOR_GROUP

logger = logging.getLogger("draws.alerts")

# Alert codes (6.5): keep in sync with docs/runbooks/draw-day.md.
DRAW_NOT_FOUND = "draw_not_found"
PARSE_FAILURE = "parse_failure"
UNKNOWN_DENOMINATION = "unknown_denomination"
UNKNOWN_LAYOUT = "unknown_layout"
REVISION_DETECTED = "revision_detected_on_published_draw"
REVIEW_OVERDUE = "review_overdue"
FETCH_FAILURE = "fetch_failure"


def operator_emails() -> list[str]:
    users = get_user_model().objects.filter(groups__name=DATA_OPERATOR_GROUP, is_active=True)
    return sorted({email for email in users.values_list("email", flat=True) if email})


def raise_alert(code: str, message: str, **context: Any) -> None:
    """Record the alert in logs and Sentry and email the operators; never raises (alerting must not break ingestion)."""
    logger.warning("draws alert %s: %s", code, message, extra={"alert_code": code, **context})
    try:
        with sentry_sdk.new_scope() as scope:
            scope.set_tag("draws.alert", code)
            scope.set_context("draws", {key: str(value) for key, value in context.items()})
            sentry_sdk.capture_message(f"[draws] {code}: {message}", level="warning")
        recipients = operator_emails()
        if recipients:
            body = message + "\n\n" + "\n".join(f"{key}: {value}" for key, value in context.items())
            send_mail(f"[Prize Bond Tracker] {code}", body, None, recipients, fail_silently=False)
    except Exception:  # noqa: BLE001 - alert delivery is best effort
        logger.exception("could not deliver draws alert %s", code)

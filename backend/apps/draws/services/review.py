"""Human review and publication of draw revisions.

A revision is published only by a data operator (with MFA) approving it. Approval supersedes the previously
published revision, moves the draw's pointer and writes the outbox event in one transaction. Nothing is ever
deleted: rolling back a bad publication means approving a corrected revision.
"""

import datetime
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.accounts.models import User
from apps.draws.models import Draw, DrawRevision, OutboxEvent
from apps.draws.rules import can_review
from apps.draws.states import check_draw_transition, check_revision_transition


class ReviewError(Exception):
    """Base class for refusals; the message is safe to show to the reviewer."""


class NotAllowed(ReviewError):
    pass


class NoteRequired(ReviewError):
    pass


class ErrorsBlockPublication(ReviewError):
    pass


class FourEyesViolation(ReviewError):
    pass


def _require_reviewer(user: User) -> None:
    if not can_review(user):
        raise NotAllowed("Only data operators with MFA enabled may review results")


def _require_note(note: str) -> str:
    note = (note or "").strip()
    if not note:
        raise NoteRequired("A written note is required")
    return note


def _locked(revision_id: Any) -> tuple[DrawRevision, Draw]:
    revision = DrawRevision.objects.select_for_update().select_related("draw__denomination").get(pk=revision_id)
    draw = Draw.objects.select_for_update().select_related("denomination").get(pk=revision.draw_id)
    return revision, draw


def _event_payload(draw: Draw, revision: DrawRevision) -> dict[str, Any]:
    return {
        "draw_id": str(draw.pk),
        "revision_id": str(revision.pk),
        "revision_no": revision.revision_no,
        "denomination": draw.denomination.slug,
        "denomination_value": draw.denomination.value_pkr,
        "draw_number": draw.draw_number,
        "draw_date": draw.draw_date.isoformat(),
    }


@transaction.atomic
def approve_revision(
    revision_id: Any, user: User, note: str, *, override_errors: bool = False, automatic: bool = False
) -> DrawRevision:
    """Publish a revision. ``override_errors`` lets a reviewer publish despite ERROR findings (needs the note)."""
    if not automatic:
        _require_reviewer(user)
    note = _require_note(note)
    revision, draw = _locked(revision_id)

    check_revision_transition(revision.status, DrawRevision.Status.APPROVED)
    if revision.parse_errors and not override_errors:
        raise ErrorsBlockPublication(f"{len(revision.parse_errors)} error finding(s) must be reviewed and overridden")
    if settings.DRAWS_FOUR_EYES and revision.uploaded_by_id is not None and revision.uploaded_by_id == user.pk:
        raise FourEyesViolation("A manual upload must be approved by someone other than the uploader")

    previous: DrawRevision | None = None
    if draw.published_revision_id:
        previous = DrawRevision.objects.select_for_update().get(pk=draw.published_revision_id)
        check_revision_transition(previous.status, DrawRevision.Status.SUPERSEDED)
        previous.status = DrawRevision.Status.SUPERSEDED
        previous.save(update_fields=["status", "updated_at"])

    now = timezone.now()
    revision.status = DrawRevision.Status.APPROVED
    revision.reviewed_by = user
    revision.reviewed_at = now
    revision.review_note = note if not (override_errors and revision.parse_errors) else f"[override] {note}"
    revision.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])

    if draw.status != Draw.Status.PUBLISHED:
        check_draw_transition(draw.status, Draw.Status.PUBLISHED)
        draw.status = Draw.Status.PUBLISHED
    draw.published_revision = revision
    draw.published_at = now
    draw.save(update_fields=["status", "published_revision", "published_at", "updated_at"])

    payload = _event_payload(draw, revision)
    if previous is None:
        OutboxEvent.objects.create(type=OutboxEvent.Type.PUBLISHED, payload=payload)
    else:
        payload["previous_revision_id"] = str(previous.pk)
        payload["diff"] = revision.diff_from_previous
        OutboxEvent.objects.create(type=OutboxEvent.Type.REVISED, payload=payload)
    return revision


@transaction.atomic
def reject_revision(revision_id: Any, user: User, note: str) -> DrawRevision:
    _require_reviewer(user)
    note = _require_note(note)
    revision, draw = _locked(revision_id)
    check_revision_transition(revision.status, DrawRevision.Status.REJECTED)
    revision.status = DrawRevision.Status.REJECTED
    revision.reviewed_by = user
    revision.reviewed_at = timezone.now()
    revision.review_note = note
    revision.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])

    still_open = draw.revisions.filter(status=DrawRevision.Status.NEEDS_REVIEW).exists()
    if draw.status == Draw.Status.IN_REVIEW and not draw.published_revision_id and not still_open:
        check_draw_transition(draw.status, Draw.Status.FAILED)
        draw.status = Draw.Status.FAILED
        draw.save(update_fields=["status", "updated_at"])
    return revision


@dataclass(frozen=True)
class BulkResult:
    approved: int
    skipped: int


def clean_backfill_candidates(older_than_days: int | None = None) -> QuerySet[DrawRevision]:
    """Historical first publications with no findings at all. Live draws and revisions are never candidates."""
    days = settings.DRAWS_HISTORICAL_AFTER_DAYS if older_than_days is None else older_than_days
    cutoff = timezone.localdate() - datetime.timedelta(days=days)
    return DrawRevision.objects.filter(
        status=DrawRevision.Status.NEEDS_REVIEW,
        parse_errors=[],
        parse_warnings=[],
        draw__published_revision__isnull=True,
        draw__draw_date__lt=cutoff,
        uploaded_by__isnull=True,
    ).exclude(extraction_method=DrawRevision.Extraction.OCR)


def bulk_approve_clean_backfill(user: User, revisions: QuerySet[DrawRevision] | None = None) -> BulkResult:
    """One-action approval of clean historical revisions (setting-gated). Every approval is audit-logged."""
    _require_reviewer(user)
    if not settings.DRAWS_AUTO_APPROVE_CLEAN_BACKFILL:
        raise NotAllowed("Bulk approval of clean backfill revisions is disabled")
    eligible = clean_backfill_candidates()
    if revisions is not None:
        eligible = eligible.filter(pk__in=revisions.values("pk"))
    approved = 0
    for revision_id in list(eligible.values_list("pk", flat=True)):
        approve_revision(revision_id, user, "Clean historical backfill: no findings", automatic=True)
        approved += 1
    skipped = (revisions.count() - approved) if revisions is not None else 0
    return BulkResult(approved=approved, skipped=max(skipped, 0))

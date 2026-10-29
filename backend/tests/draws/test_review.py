import datetime

import pytest
from django.contrib.auth.models import Group

from apps.draws.models import Draw, DrawRevision, OutboxEvent
from apps.draws.rules import can_review, can_upload
from apps.draws.services import pipeline, review
from apps.draws.states import IllegalTransition
from tests.draws.conftest import SEPT_15, fixture_bytes, make_operator, rs200
from tests.draws.factories import DrawFactory, RevisionFactory
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

DRAW_107 = fixture_bytes("rs-200-prize-bond-draw/200_150926.txt")
DRAW_108_750 = fixture_bytes("rs-750-prize-bond-draw/750_15102026-1.txt")


@pytest.fixture
def revision(sent_alerts):
    draw, _ = pipeline.get_or_create_draw(rs200(), SEPT_15)
    return pipeline.create_revision(draw, DRAW_107, "txt")


@pytest.fixture
def revision_with_error(sent_alerts):
    draw, _ = pipeline.get_or_create_draw(rs200().__class__.objects.get(slug="rs-750"), datetime.date(2026, 10, 15))
    return pipeline.create_revision(draw, DRAW_108_750, "txt")


# --- permissions -----------------------------------------------------------------------------------------------------


def test_only_data_operators_with_mfa_may_review_or_upload(operator):
    assert can_review(operator) and can_upload(operator)
    assert not can_review(make_operator(mfa=False))
    assert not can_upload(make_operator(mfa=False))
    assert not can_review(UserFactory())  # no group
    assert not can_review(UserFactory(is_superuser=True, is_staff=True))  # superusers do not bypass the rules
    group_without_mfa = UserFactory()
    group_without_mfa.groups.add(Group.objects.get(name="data_operator"))
    assert not can_review(group_without_mfa)


def test_anonymous_and_inactive_users_have_no_review_rights(operator):
    from django.contrib.auth.models import AnonymousUser

    assert not can_review(AnonymousUser())
    operator.is_active = False
    operator.save()
    assert not can_review(operator)


def test_non_operators_cannot_approve_or_reject(revision):
    stranger = UserFactory()
    with pytest.raises(review.NotAllowed):
        review.approve_revision(revision.pk, stranger, "ok")
    with pytest.raises(review.NotAllowed):
        review.reject_revision(revision.pk, stranger, "no")
    revision.refresh_from_db()
    assert revision.status == DrawRevision.Status.NEEDS_REVIEW


# --- approve ---------------------------------------------------------------------------------------------------------


def test_approving_publishes_the_draw_and_writes_the_outbox_event(revision, operator):
    approved = review.approve_revision(revision.pk, operator, " looks right ")
    approved.refresh_from_db()
    draw = Draw.objects.get(pk=revision.draw_id)
    assert approved.status == DrawRevision.Status.APPROVED
    assert (approved.reviewed_by, approved.review_note) == (operator, "looks right")
    assert approved.reviewed_at is not None
    assert draw.status == Draw.Status.PUBLISHED
    assert draw.published_revision_id == revision.pk
    assert draw.published_at is not None
    [event] = OutboxEvent.objects.all()
    assert event.type == "draw.published"
    assert event.processed_at is None
    assert event.payload["draw_number"] == 107 and event.payload["denomination"] == "rs-200"
    assert event.payload["revision_id"] == str(revision.pk)


def test_a_note_is_always_required(revision, operator):
    for note in ("", "   ", None):
        with pytest.raises(review.NoteRequired):
            review.approve_revision(revision.pk, operator, note)
    with pytest.raises(review.NoteRequired):
        review.reject_revision(revision.pk, operator, "")


def test_errors_block_publication_until_overridden_with_a_note(revision_with_error, operator):
    with pytest.raises(review.ErrorsBlockPublication):
        review.approve_revision(revision_with_error.pk, operator, "ok")
    assert not OutboxEvent.objects.exists()
    approved = review.approve_revision(
        revision_with_error.pk, operator, "Checked against the PDF: 7447 is printed as such", override_errors=True
    )
    assert approved.review_note.startswith("[override] ")
    assert Draw.objects.get(pk=approved.draw_id).status == Draw.Status.PUBLISHED


def test_four_eyes_forbids_approving_your_own_upload(sent_alerts, operator, other_operator, settings):
    settings.DRAWS_FOUR_EYES = True
    uploaded = pipeline.upload_revision(rs200(), SEPT_15, DRAW_107, "r.txt", operator, max_bytes=10**6)
    with pytest.raises(review.FourEyesViolation):
        review.approve_revision(uploaded.pk, operator, "mine")
    assert review.approve_revision(uploaded.pk, other_operator, "second pair of eyes").status == "APPROVED"


def test_four_eyes_can_be_switched_off_and_never_applies_to_crawled_files(
    sent_alerts, operator, other_operator, settings, revision
):
    settings.DRAWS_FOUR_EYES = True
    assert review.approve_revision(revision.pk, operator, "crawled, no uploader").status == "APPROVED"
    settings.DRAWS_FOUR_EYES = False
    draw = DrawFactory(draw_date=datetime.date(2020, 5, 5))
    own = pipeline.upload_revision(draw.denomination, draw.draw_date, DRAW_107, "r.txt", operator, max_bytes=10**6)
    assert review.approve_revision(own.pk, operator, "allowed in dev", override_errors=True).status == "APPROVED"


def test_a_revision_supersedes_the_published_one_and_emits_draw_revised(revision, operator, sent_alerts):
    review.approve_revision(revision.pk, operator, "first")
    corrected = pipeline.create_revision(revision.draw, DRAW_107.replace(b"516806", b"516807"), "txt")
    assert corrected.revision_no == 2
    review.approve_revision(corrected.pk, operator, "corrected the first prize")

    revision.refresh_from_db()
    draw = Draw.objects.get(pk=revision.draw_id)
    assert revision.status == DrawRevision.Status.SUPERSEDED
    assert draw.published_revision_id == corrected.pk
    assert [e.type for e in OutboxEvent.objects.order_by("created_at")] == ["draw.published", "draw.revised"]
    revised = OutboxEvent.objects.get(type="draw.revised")
    assert revised.payload["previous_revision_id"] == str(revision.pk)
    assert revised.payload["diff"]["tiers"]["1"]["added"] == ["516807"]
    assert revised.payload["diff"]["tiers"]["1"]["removed"] == ["516806"]
    assert DrawRevision.objects.count() == 2  # nothing is ever deleted


def test_rolling_back_a_bad_publication_is_approving_a_corrected_revision(revision, operator, sent_alerts):
    review.approve_revision(revision.pk, operator, "published")
    bad = pipeline.create_revision(revision.draw, DRAW_107.replace(b"516806", b"999999"), "txt")
    review.approve_revision(bad.pk, operator, "oops")
    corrected = pipeline.create_revision(revision.draw, DRAW_107.replace(b"516806", b"516808"), "txt")
    review.approve_revision(corrected.pk, operator, "rollback to the verified numbers")
    assert Draw.objects.get(pk=revision.draw_id).published_revision_id == corrected.pk
    assert DrawRevision.objects.filter(status=DrawRevision.Status.SUPERSEDED).count() == 2


def test_illegal_transitions_are_refused(revision, operator):
    approved = review.approve_revision(revision.pk, operator, "ok")
    with pytest.raises(IllegalTransition):
        review.approve_revision(approved.pk, operator, "again")
    with pytest.raises(IllegalTransition):
        review.reject_revision(approved.pk, operator, "too late")


def test_publication_is_atomic_when_the_outbox_write_fails(revision, operator, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("outbox down")

    monkeypatch.setattr(OutboxEvent.objects, "create", boom)
    with pytest.raises(RuntimeError):
        review.approve_revision(revision.pk, operator, "ok")
    revision.refresh_from_db()
    draw = Draw.objects.get(pk=revision.draw_id)
    assert revision.status == DrawRevision.Status.NEEDS_REVIEW
    assert draw.published_revision_id is None and draw.status == Draw.Status.IN_REVIEW


def test_supersede_and_publish_are_atomic(revision, operator, sent_alerts, monkeypatch):
    review.approve_revision(revision.pk, operator, "first")
    second = pipeline.create_revision(revision.draw, DRAW_107.replace(b"516806", b"516807"), "txt")

    def boom(*args, **kwargs):
        raise RuntimeError("outbox down")

    monkeypatch.setattr(OutboxEvent.objects, "create", boom)
    with pytest.raises(RuntimeError):
        review.approve_revision(second.pk, operator, "second")
    revision.refresh_from_db()
    assert revision.status == DrawRevision.Status.APPROVED  # the supersede was rolled back too
    assert Draw.objects.get(pk=revision.draw_id).published_revision_id == revision.pk


# --- reject ----------------------------------------------------------------------------------------------------------


def test_rejecting_marks_the_revision_and_fails_a_draw_with_nothing_else_open(revision, operator):
    rejected = review.reject_revision(revision.pk, operator, "wrong file")
    assert rejected.status == DrawRevision.Status.REJECTED
    assert rejected.review_note == "wrong file"
    assert Draw.objects.get(pk=revision.draw_id).status == Draw.Status.FAILED
    assert not OutboxEvent.objects.exists()


def test_rejecting_one_of_two_open_revisions_keeps_the_draw_in_review(revision, operator, sent_alerts):
    other = pipeline.create_revision(revision.draw, DRAW_107.replace(b"516806", b"516807"), "txt")
    review.reject_revision(revision.pk, operator, "superseded by the next file")
    assert Draw.objects.get(pk=revision.draw_id).status == Draw.Status.IN_REVIEW
    assert DrawRevision.objects.get(pk=other.pk).status == DrawRevision.Status.NEEDS_REVIEW


def test_a_failed_parse_can_be_rejected(operator, sent_alerts):
    draw, _ = pipeline.get_or_create_draw(rs200(), SEPT_15)
    failed = pipeline.create_revision(draw, b"%PDF-1.4 nope", "pdf")
    assert review.reject_revision(failed.pk, operator, "garbage").status == DrawRevision.Status.REJECTED


# --- bulk approval of clean backfill ---------------------------------------------------------------------------------


def clean_revision(days_ago: int, **overrides):
    draw = DrawFactory(
        draw_date=datetime.date.today() - datetime.timedelta(days=days_ago), status=Draw.Status.IN_REVIEW
    )
    return RevisionFactory(
        draw=draw, status=DrawRevision.Status.NEEDS_REVIEW, parse_errors=[], parse_warnings=[], **overrides
    )


def test_bulk_approve_takes_clean_historical_revisions_only(operator):
    old_clean = clean_revision(400)
    live = clean_revision(3)
    warned = clean_revision(401)
    warned.parse_warnings = [{"code": "x"}]
    warned.save(update_fields=["parse_warnings"])
    errored = clean_revision(402)
    errored.parse_errors = [{"code": "y"}]
    errored.save(update_fields=["parse_errors"])
    ocr = clean_revision(403, extraction_method=DrawRevision.Extraction.OCR)
    uploaded = clean_revision(404, uploaded_by=UserFactory())

    result = review.bulk_approve_clean_backfill(operator)

    assert result.approved == 1
    assert DrawRevision.objects.get(pk=old_clean.pk).status == DrawRevision.Status.APPROVED
    for untouched in (live, warned, errored, ocr, uploaded):
        assert DrawRevision.objects.get(pk=untouched.pk).status == DrawRevision.Status.NEEDS_REVIEW
    assert OutboxEvent.objects.filter(type="draw.published").count() == 1


def test_bulk_approve_needs_a_reviewer_and_the_setting(operator, settings):
    clean_revision(400)
    with pytest.raises(review.NotAllowed):
        review.bulk_approve_clean_backfill(UserFactory())
    settings.DRAWS_AUTO_APPROVE_CLEAN_BACKFILL = False
    with pytest.raises(review.NotAllowed, match="disabled"):
        review.bulk_approve_clean_backfill(operator)


def test_bulk_approve_can_be_limited_to_a_queryset(operator):
    first, second = clean_revision(400), clean_revision(500)
    result = review.bulk_approve_clean_backfill(operator, DrawRevision.objects.filter(pk=first.pk))
    assert result.approved == 1
    assert DrawRevision.objects.get(pk=second.pk).status == DrawRevision.Status.NEEDS_REVIEW


def test_approvals_are_audit_logged(revision, operator):
    from auditlog.models import LogEntry

    review.approve_revision(revision.pk, operator, "audit me")
    entries = LogEntry.objects.filter(object_pk=str(revision.pk))
    assert any("status" in (e.changes_dict or {}) for e in entries)

import datetime

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.draws.models import Draw, DrawRevision, DrawSchedule, OutboxEvent
from apps.draws.services import pipeline
from tests.draws.conftest import SEPT_15, fixture_bytes, make_operator, rs200
from tests.draws.factories import DrawFactory, RevisionFactory
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

BACKEND = "django.contrib.auth.backends.ModelBackend"
DRAW_107 = fixture_bytes("rs-200-prize-bond-draw/200_150926.txt")
DRAW_108_750 = fixture_bytes("rs-750-prize-bond-draw/750_15102026-1.txt")


@pytest.fixture
def logged_in(client, operator):
    client.force_login(operator, backend=BACKEND)
    return client


@pytest.fixture
def revision(sent_alerts):
    draw, _ = pipeline.get_or_create_draw(rs200(), SEPT_15)
    return pipeline.create_revision(draw, DRAW_107, "txt")


@pytest.fixture
def revision_with_error(sent_alerts):
    draw, _ = pipeline.get_or_create_draw(rs200().__class__.objects.get(slug="rs-750"), datetime.date(2026, 10, 15))
    return pipeline.create_revision(draw, DRAW_108_750, "txt")


def review_url(revision):
    return reverse("admin:draws_drawrevision_review", args=[revision.pk])


# --- access --------------------------------------------------------------------------------------------------------


def test_anonymous_cannot_reach_the_queue(client):
    assert (
        client.get(reverse("admin:draws_drawrevision_changelist"), follow=True)
        .redirect_chain[-1][0]
        .startswith("/accounts/login/")
    )


@pytest.mark.parametrize(
    "who",
    ["staff_with_mfa_but_no_group", "operator_without_mfa", "superuser_without_group"],
)
def test_people_who_are_not_mfa_operators_get_nothing(client, who, revision):
    from allauth.mfa.models import Authenticator

    if who == "staff_with_mfa_but_no_group":
        user = UserFactory(is_staff=True)
        Authenticator.objects.create(user=user, type=Authenticator.Type.TOTP, data={"secret": "x"})
    elif who == "operator_without_mfa":
        user = make_operator(mfa=False)
    else:
        user = UserFactory(is_staff=True, is_superuser=True)
        Authenticator.objects.create(user=user, type=Authenticator.Type.TOTP, data={"secret": "x"})
    client.force_login(user, backend=BACKEND)
    urls = (
        reverse("admin:draws_drawrevision_changelist"),
        review_url(revision),
        reverse("admin:draws_drawrevision_upload"),
    )
    for url in urls:
        response = client.get(url, follow=True)
        # Either refused outright (no operator rights) or bounced to the allauth login (staff without MFA).
        assert response.status_code == 403 or response.redirect_chain[-1][0].startswith(
            ("/accounts/login", "/admin/login")
        )
        body = response.content.decode()
        assert "Announced vs parsed counts" not in body
        assert "Upload and parse" not in body
    assert client.post(review_url(revision), {"decision": "approve", "note": "x"}).status_code in (302, 403)
    assert DrawRevision.objects.get(pk=revision.pk).status == DrawRevision.Status.NEEDS_REVIEW


# --- queue ----------------------------------------------------------------------------------------------------------


def test_the_queue_defaults_to_revisions_needing_review(logged_in, revision):
    done = RevisionFactory(status=DrawRevision.Status.APPROVED)
    response = logged_in.get(reverse("admin:draws_drawrevision_changelist"), follow=True)
    assert response.redirect_chain[0][0].endswith("?status__exact=NEEDS_REVIEW")
    body = response.content.decode()
    assert review_url(revision) in body
    assert review_url(done) not in body
    assert "Upload a result manually" in body


# --- review screen ---------------------------------------------------------------------------------------------------


def test_review_screen_shows_everything_a_reviewer_needs(logged_in, revision_with_error):
    body = logged_in.get(review_url(revision_with_error)).content.decode()
    assert "Announced vs parsed counts" in body
    assert "wrong_digit_length" in body  # the error finding
    assert "Second Prize" in body  # source excerpt around a tier heading
    assert "7447" in body  # the offending number is visible next to its source line
    assert "750 DENOMINATION" in body.upper() or "RS.750" in body.upper()
    assert 'name="decision"' in body


def test_review_screen_shows_the_diff_for_later_revisions(logged_in, revision, sent_alerts):
    second = pipeline.create_revision(revision.draw, DRAW_107.replace(b"516806", b"516807"), "txt")
    body = logged_in.get(review_url(second)).content.decode()
    assert "516807" in body and "516806" in body
    assert "2 number(s) changed" in body


def test_missing_raw_file_is_reported_not_a_crash(logged_in, revision, settings, tmp_path):
    settings.STORAGES = {
        **settings.STORAGES,
        "draws_raw": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path / "gone")},
        },
    }
    body = logged_in.get(review_url(revision)).content.decode()
    assert "could not be re-read" in body


# --- decisions -------------------------------------------------------------------------------------------------------


def test_approve_requires_a_note_and_then_publishes(logged_in, revision):
    response = logged_in.post(review_url(revision), {"decision": "approve", "note": "  "})
    assert response.status_code == 200
    assert DrawRevision.objects.get(pk=revision.pk).status == DrawRevision.Status.NEEDS_REVIEW

    response = logged_in.post(review_url(revision), {"decision": "approve", "note": "verified on the PDF"})
    assert response.status_code == 302
    assert DrawRevision.objects.get(pk=revision.pk).status == DrawRevision.Status.APPROVED
    assert Draw.objects.get(pk=revision.draw_id).status == Draw.Status.PUBLISHED
    assert OutboxEvent.objects.filter(type="draw.published").count() == 1


def test_errors_need_the_override_box(logged_in, revision_with_error):
    blocked = logged_in.post(review_url(revision_with_error), {"decision": "approve", "note": "ok"}, follow=True)
    assert "must be reviewed and overridden" in blocked.content.decode()
    assert DrawRevision.objects.get(pk=revision_with_error.pk).status == DrawRevision.Status.NEEDS_REVIEW

    logged_in.post(
        review_url(revision_with_error), {"decision": "approve", "note": "7447 is printed", "override_errors": "on"}
    )
    assert DrawRevision.objects.get(pk=revision_with_error.pk).status == DrawRevision.Status.APPROVED


def test_reject_needs_a_note(logged_in, revision):
    assert logged_in.post(review_url(revision), {"decision": "reject", "note": ""}).status_code == 200
    assert logged_in.post(review_url(revision), {"decision": "reject", "note": "wrong draw"}).status_code == 302
    assert DrawRevision.objects.get(pk=revision.pk).status == DrawRevision.Status.REJECTED


def test_unknown_decision_is_refused(logged_in, revision):
    response = logged_in.post(review_url(revision), {"decision": "maybe", "note": "hmm"})
    assert response.status_code == 200
    assert "Choose Approve or Reject" in response.content.decode()


def test_deciding_twice_shows_the_error_instead_of_crashing(logged_in, revision):
    logged_in.post(review_url(revision), {"decision": "approve", "note": "first"})
    again = logged_in.post(review_url(revision), {"decision": "approve", "note": "second"})
    assert again.status_code == 200
    assert "Illegal revision transition" in again.content.decode()


# --- manual upload and four-eyes --------------------------------------------------------------------------------------


def upload(client, content=DRAW_107, name="result.txt", denomination=None, date="2026-09-15"):
    denomination = denomination or rs200()
    return client.post(
        reverse("admin:draws_drawrevision_upload"),
        {"denomination": denomination.pk, "draw_date": date, "file": SimpleUploadedFile(name, content)},
    )


def test_upload_form_runs_the_pipeline_and_redirects_to_the_review_screen(logged_in, sent_alerts):
    assert logged_in.get(reverse("admin:draws_drawrevision_upload")).status_code == 200
    response = upload(logged_in)
    assert response.status_code == 302
    revision = DrawRevision.objects.get()
    assert response["Location"] == review_url(revision)
    assert revision.uploaded_by is not None and revision.status == DrawRevision.Status.NEEDS_REVIEW


def test_upload_rejects_unsupported_files(logged_in, sent_alerts):
    response = upload(logged_in, b"MZ", "virus.exe")
    assert response.status_code == 200
    assert "Unsupported file type" in response.content.decode()
    assert not DrawRevision.objects.exists()


def test_four_eyes_in_the_admin(client, settings, sent_alerts, operator, other_operator):
    settings.DRAWS_FOUR_EYES = True
    client.force_login(operator, backend=BACKEND)
    upload(client)
    revision = DrawRevision.objects.get()
    mine = client.post(review_url(revision), {"decision": "approve", "note": "mine"})
    assert "someone other than the uploader" in mine.content.decode()
    client.force_login(other_operator, backend=BACKEND)
    assert client.post(review_url(revision), {"decision": "approve", "note": "second pair"}).status_code == 302
    assert DrawRevision.objects.get(pk=revision.pk).status == DrawRevision.Status.APPROVED


# --- bulk action and other models ------------------------------------------------------------------------------------


def clean_revision(days_ago):
    draw = DrawFactory(
        draw_date=datetime.date.today() - datetime.timedelta(days=days_ago), status=Draw.Status.IN_REVIEW
    )
    return RevisionFactory(draw=draw, status=DrawRevision.Status.NEEDS_REVIEW, parse_errors=[], parse_warnings=[])


def test_bulk_action_approves_only_clean_historical_revisions(logged_in):
    old, live = clean_revision(500), clean_revision(2)
    response = logged_in.post(
        reverse("admin:draws_drawrevision_changelist") + "?status__exact=NEEDS_REVIEW",
        {"action": "approve_clean_backfill", "_selected_action": [str(old.pk), str(live.pk)]},
        follow=True,
    )
    assert "Approved 1 clean revision(s)" in response.content.decode()
    assert DrawRevision.objects.get(pk=old.pk).status == DrawRevision.Status.APPROVED
    assert DrawRevision.objects.get(pk=live.pk).status == DrawRevision.Status.NEEDS_REVIEW


def test_bulk_action_reports_when_disabled(logged_in, settings):
    settings.DRAWS_AUTO_APPROVE_CLEAN_BACKFILL = False
    old = clean_revision(500)
    response = logged_in.post(
        reverse("admin:draws_drawrevision_changelist") + "?status__exact=NEEDS_REVIEW",
        {"action": "approve_clean_backfill", "_selected_action": [str(old.pk)]},
        follow=True,
    )
    assert "disabled" in response.content.decode()


def test_revisions_cannot_be_added_changed_or_deleted_in_the_admin(logged_in, revision):
    assert logged_in.get(reverse("admin:draws_drawrevision_add")).status_code == 403
    assert logged_in.get(reverse("admin:draws_drawrevision_delete", args=[revision.pk])).status_code == 403
    assert logged_in.get(reverse("admin:draws_draw_delete", args=[revision.draw_id])).status_code == 403


def test_operators_maintain_the_draw_schedule(logged_in):
    response = logged_in.post(
        reverse("admin:draws_drawschedule_add"),
        {"denomination": rs200().pk, "scheduled_date": "2027-03-15", "city": "Multan"},
    )
    assert response.status_code == 302
    assert DrawSchedule.objects.get().city == "Multan"


def test_read_only_pages_render_for_operators(logged_in, revision):
    for name in (
        "draws_draw_changelist",
        "draws_denomination_changelist",
        "draws_ingestionrun_changelist",
        "draws_outboxevent_changelist",
    ):
        assert logged_in.get(reverse(f"admin:{name}")).status_code == 200

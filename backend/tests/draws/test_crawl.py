import datetime

import pytest
import respx
from django.utils import timezone

from apps.draws import alerts, tasks
from apps.draws.models import Draw, DrawRevision, DrawSchedule, IngestionRun, OutboxEvent
from apps.draws.services import crawl, review
from tests.draws.conftest import rs200
from tests.draws.factories import DrawFactory, RevisionFactory
from tests.draws.site import Clock, FakeSite, make_fetcher

pytestmark = pytest.mark.django_db

KARACHI = datetime.timezone(datetime.timedelta(hours=5))
SEPT_LINK = "200_150926.txt"
SEPT_DAY = datetime.date(2026, 9, 15)


@pytest.fixture
def site():
    with respx.mock(assert_all_called=False) as router:
        yield FakeSite(router)


@pytest.fixture
def fetcher():
    return make_fetcher(Clock())


def at(hour, minute=0, day=SEPT_DAY):
    return datetime.datetime.combine(day, datetime.time(hour, minute), tzinfo=KARACHI)


# --- discovery crawl ---------------------------------------------------------------------------------------------------


def test_a_crawl_discovers_downloads_parses_and_queues_revisions(site, fetcher, sent_alerts):
    result = crawl.run_crawl(fetcher, "SCHEDULE", slugs=["rs-200"], since_year=2026)
    assert (result.stats.files_new, result.stats.files_failed) == (3, 0)
    run = result.run
    assert (run.outcome, run.trigger, run.files_new, run.pages_fetched) == ("SUCCESS", "SCHEDULE", 3, 2)  # index + page
    assert run.finished_at is not None
    assert sorted(Draw.objects.values_list("draw_number", flat=True)) == [105, 106, 107]
    assert set(DrawRevision.objects.values_list("status", flat=True)) == {"NEEDS_REVIEW"}
    assert Draw.objects.get(draw_number=107).draw_date == SEPT_DAY


def test_a_second_crawl_is_a_no_op(site, fetcher, sent_alerts):
    crawl.run_crawl(fetcher, "SCHEDULE", slugs=["rs-200"], since_year=2026)
    again = crawl.run_crawl(fetcher, "SCHEDULE", slugs=["rs-200"], since_year=2026)
    assert (again.stats.files_new, again.stats.files_unchanged) == (0, 3)
    assert DrawRevision.objects.count() == 3
    assert IngestionRun.objects.count() == 2


def test_files_that_fail_are_counted_and_the_run_is_partial(site, fetcher, sent_alerts):
    site.unavailable.add("https://savings.gov.pk/wp-content/uploads/2026/06/Rs-200-15-06-2026-106-draw.txt")
    result = crawl.run_crawl(fetcher, "SCHEDULE", slugs=["rs-200"], since_year=2026)
    assert (result.stats.files_new, result.stats.files_failed) == (2, 1)
    assert result.run.outcome == IngestionRun.Outcome.PARTIAL
    assert alerts.FETCH_FAILURE in [a[0] for a in sent_alerts]


def test_an_unreachable_page_fails_the_run(site, fetcher, sent_alerts):
    site.unavailable.add("https://savings.gov.pk/download-draws/")
    site.unavailable.add("https://savings.gov.pk/rs-200-prize-bond-draw/")
    result = crawl.run_crawl(fetcher, "SCHEDULE", slugs=["rs-200"])
    assert result.run.outcome == IngestionRun.Outcome.FAILED
    assert "rs-200" in result.run.error_summary


def test_an_unknown_denomination_is_alerted_and_never_created(site, fetcher, sent_alerts):
    site.index = site.index.replace(
        "</body>", '<a href="/rs-7500-prize-bond-draw">Rs. 7500 Prize Bond Draw List</a></body>'
    )
    before = set(crawl.Denomination.objects.values_list("slug", flat=True))
    crawl.run_crawl(fetcher, "SCHEDULE", slugs=["rs-200"], since_year=2027)
    assert alerts.UNKNOWN_DENOMINATION in [a[0] for a in sent_alerts]
    assert set(crawl.Denomination.objects.values_list("slug", flat=True)) == before


def test_a_link_without_a_date_is_alerted_and_skipped(site, fetcher, sent_alerts):
    undated = '<h2><a href="/wp-content/uploads/2026/10/latest-result.txt">latest results</a></h2>'
    assert ">2026</h2>" in site.pages["rs-200"]
    site.pages["rs-200"] = site.pages["rs-200"].replace(">2026</h2>", ">2026</h2>" + undated, 1)
    result = crawl.run_crawl(fetcher, "SCHEDULE", slugs=["rs-200"], since_year=2027)
    assert result.stats.undated_links == 1
    assert alerts.UNKNOWN_LAYOUT in [a[0] for a in sent_alerts]
    assert result.run.outcome == IngestionRun.Outcome.PARTIAL


def test_requests_are_spaced_out_and_identify_the_crawler(site, fetcher, sent_alerts):
    crawl.run_crawl(fetcher, "SCHEDULE", slugs=["rs-200"], since_year=2026)
    calls = [c.request for c in site.router.calls]
    assert {c.headers["user-agent"] for c in calls} == {"Test/1.0 (+mailto:ops@example.com)"}
    assert all(c.url.host == "savings.gov.pk" for c in calls)


def test_dry_run_writes_nothing_and_summarises_findings(site, fetcher, sent_alerts):
    result = crawl.run_crawl(fetcher, "BACKFILL", slugs=["rs-200"], since_year=2026, dry_run=True)
    assert result.run is None
    assert not DrawRevision.objects.exists() and not Draw.objects.exists() and not IngestionRun.objects.exists()
    rows = {row["date"]: row for row in result.stats.dry_rows}
    assert set(rows) == {"2026-03-16", "2026-06-15", "2026-09-15"}
    assert "announced_count_is_total" in rows["2026-09-15"]["warnings"]
    assert rows["2026-09-15"]["status"] == "warnings"


# --- draw-day polling: the end-to-end story ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (at(11, 30), False),  # before the window opens
        (at(12, 0), True),
        (at(18, 30), True),
        (at(23, 30), True),
        (at(23, 59), False),
        (at(12, 0, SEPT_DAY - datetime.timedelta(days=1)), False),  # before the draw day
        (at(12, 0, SEPT_DAY + datetime.timedelta(days=1)), True),  # hourly after: the :00 run
        (at(12, 30, SEPT_DAY + datetime.timedelta(days=1)), False),  # no :30 run after the draw day
        (at(15, 0, SEPT_DAY + datetime.timedelta(days=3)), True),
        (at(15, 0, SEPT_DAY + datetime.timedelta(days=4)), False),  # polling stops after three days
    ],
)
def test_polling_window(now, expected):
    assert crawl.in_polling_window(SEPT_DAY, now) is expected


def test_draw_day_polling_finds_queues_publishes_and_emits_the_event(site, fetcher, sent_alerts, operator):
    DrawSchedule.objects.create(denomination=rs200(), scheduled_date=SEPT_DAY, city="Muzaffarabad")
    site.drop_link("rs-200", SEPT_LINK)  # the file has not been published yet

    # 12:00 - not there yet: nothing is created.
    crawl.poll_draw_day(fetcher, at(12, 0))
    assert not Draw.objects.exists()

    # 12:30 - the site publishes it; the next poll finds it, parses it and queues it for review.
    site.pages["rs-200"] = site.original_pages["rs-200"]  # the original page, with the link back
    results = crawl.poll_draw_day(fetcher, at(12, 30))
    assert [r.run.trigger for r in results] == ["DRAW_DAY"]
    revision = DrawRevision.objects.get()
    assert revision.status == DrawRevision.Status.NEEDS_REVIEW
    assert revision.draw.draw_date == SEPT_DAY

    # Found: later polls on the same day stop making requests.
    seen = len(site.request_log)
    assert crawl.poll_draw_day(fetcher, at(13, 0)) == []
    assert len(site.request_log) == seen

    # A data operator approves; the draw is published and the outbox event is written in the same transaction.
    review.approve_revision(revision.pk, operator, "checked against the PDF")
    assert Draw.objects.get().status == Draw.Status.PUBLISHED
    [event] = OutboxEvent.objects.all()
    assert event.type == "draw.published" and event.processed_at is None

    # The Phase 1 consumer logs and marks it processed.
    assert crawl.process_outbox() == 1
    assert OutboxEvent.objects.get().processed_at is not None
    assert crawl.process_outbox() == 0


def test_polling_ignores_schedules_outside_their_window(site, fetcher, sent_alerts):
    DrawSchedule.objects.create(denomination=rs200(), scheduled_date=SEPT_DAY)
    assert crawl.poll_draw_day(fetcher, at(9, 0)) == []
    assert crawl.poll_draw_day(fetcher, at(12, 0, SEPT_DAY + datetime.timedelta(days=10))) == []
    assert site.request_log == []


def test_a_revised_file_becomes_revision_two_with_a_diff_and_draw_revised_on_approval(
    site, fetcher, sent_alerts, operator
):
    crawl.run_crawl(fetcher, "SCHEDULE", slugs=["rs-200"], since_year=2026)
    draw = Draw.objects.get(draw_number=107)
    review.approve_revision(draw.revisions.get().pk, operator, "published")

    url = f"https://savings.gov.pk/wp-content/uploads/2026/09/{SEPT_LINK}"
    site.files[url] = site.files[url].replace(b"516806", b"516807")  # NSS replaces the file in place
    result = crawl.run_crawl(fetcher, "SCHEDULE", slugs=["rs-200"], since_year=2026)
    assert result.stats.files_new == 1
    revision = draw.revisions.get(revision_no=2)
    assert revision.diff_from_previous["tiers"]["1"]["added"] == ["516807"]
    assert revision.diff_from_previous["tiers"]["1"]["removed"] == ["516806"]
    assert alerts.REVISION_DETECTED in [a[0] for a in sent_alerts]
    draw.refresh_from_db()
    assert draw.status == Draw.Status.PUBLISHED  # users keep seeing the approved revision until review

    review.approve_revision(revision.pk, operator, "NSS corrected the first prize")
    revised = OutboxEvent.objects.get(type="draw.revised")
    assert revised.payload["diff"]["changed_numbers"] == 2
    assert DrawRevision.objects.get(revision_no=1, draw=draw).status == DrawRevision.Status.SUPERSEDED


# --- watchdogs and tasks -----------------------------------------------------------------------------------------------


def test_missing_draw_alerts_once_three_days_after_the_schedule(sent_alerts):
    schedule = DrawSchedule.objects.create(denomination=rs200(), scheduled_date=SEPT_DAY)
    assert crawl.check_missing_draws(at(10, 0, SEPT_DAY + datetime.timedelta(days=3))) == 0  # not yet 3 days past
    assert crawl.check_missing_draws(at(10, 0, SEPT_DAY + datetime.timedelta(days=4))) == 1
    assert crawl.check_missing_draws(at(10, 0, SEPT_DAY + datetime.timedelta(days=5))) == 0  # only once
    assert [a[0] for a in sent_alerts] == [alerts.DRAW_NOT_FOUND]
    schedule.refresh_from_db()
    assert schedule.missing_alerted_at is not None


def test_no_missing_alert_when_the_draw_was_found(sent_alerts):
    DrawSchedule.objects.create(denomination=rs200(), scheduled_date=SEPT_DAY)
    RevisionFactory(draw=DrawFactory(denomination=rs200(), draw_date=SEPT_DAY))
    assert crawl.check_missing_draws(at(10, 0, SEPT_DAY + datetime.timedelta(days=9))) == 0
    assert sent_alerts == []


def test_overdue_review_alerts_once_after_24_hours(sent_alerts):
    revision = RevisionFactory(status=DrawRevision.Status.NEEDS_REVIEW)
    DrawRevision.objects.filter(pk=revision.pk).update(created_at=timezone.now() - datetime.timedelta(hours=25))
    fresh = RevisionFactory(status=DrawRevision.Status.NEEDS_REVIEW)
    assert crawl.check_overdue_reviews() == 1
    assert crawl.check_overdue_reviews() == 0
    assert [a[0] for a in sent_alerts] == [alerts.REVIEW_OVERDUE]
    assert DrawRevision.objects.get(pk=fresh.pk).overdue_alerted_at is None


def test_tasks_run_the_same_code_and_close_the_fetcher(site, monkeypatch, sent_alerts):
    made = []

    def fake_make():
        made.append(make_fetcher(Clock()))
        return made[-1]

    real_crawl = crawl.run_crawl
    monkeypatch.setattr(crawl, "make_fetcher", fake_make)
    # Keep the test small: one denomination, 2026 only.
    monkeypatch.setattr(crawl, "run_crawl", lambda f, t, **kw: real_crawl(f, t, slugs=["rs-200"], since_year=2026))

    summary = tasks.discover()
    assert (summary["new"], summary["failed"], summary["pages"]) == (3, 0, 2)
    assert IngestionRun.objects.get().trigger == "SCHEDULE"
    assert made[0].client.is_closed

    assert tasks.revision_watch()["unchanged"] == 3
    assert made[1].client.is_closed

    monkeypatch.setattr(crawl, "poll_draw_day", lambda fetcher: ["a", "b"])
    assert tasks.poll_draw_day() == 2
    assert made[2].client.is_closed
    assert tasks.check_missing_draws() == 0 and tasks.check_overdue_reviews() == 0 and tasks.process_outbox() == 0


def test_beat_schedule_and_queue_routing_match_the_spec(settings):
    schedule = settings.CELERY_BEAT_SCHEDULE
    daily = schedule["draws-discover-daily"]["schedule"]
    assert (daily.hour, daily.minute) == ({9}, {10})
    poll = schedule["draws-poll-draw-day"]["schedule"]
    assert poll.hour == set(range(12, 24)) and poll.minute == {0, 30}
    assert schedule["draws-revision-watch-weekly"]["schedule"].day_of_week == {0}
    assert {entry["task"] for entry in schedule.values()} >= {
        "draws.discover",
        "draws.poll_draw_day",
        "draws.revision_watch",
        "draws.check_missing_draws",
        "draws.check_overdue_reviews",
        "draws.process_outbox",
    }
    assert settings.CELERY_TASK_ROUTES == {"draws.*": {"queue": "ingestion"}}
    assert settings.TIME_ZONE == settings.CELERY_TIMEZONE == "Asia/Karachi"

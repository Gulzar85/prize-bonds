"""Celery tasks. All of them run on the dedicated ``ingestion`` queue (see CELERY_TASK_ROUTES)."""

from typing import Any

from celery import shared_task

from apps.draws.models import IngestionRun
from apps.draws.services import crawl


def _crawl(trigger: str) -> dict[str, Any]:
    fetcher = crawl.make_fetcher()
    try:
        result = crawl.run_crawl(fetcher, trigger)
    finally:
        fetcher.close()
    stats = result.stats
    return {
        "run": str(result.run.pk) if result.run else None,
        "pages": stats.pages_fetched,
        "new": stats.files_new,
        "unchanged": stats.files_unchanged,
        "failed": stats.files_failed,
    }


@shared_task(name="draws.discover")
def discover() -> dict[str, Any]:
    """Daily 09:10 Asia/Karachi: crawl every denomination page for new files."""
    return _crawl(IngestionRun.Trigger.SCHEDULE)


@shared_task(name="draws.revision_watch")
def revision_watch() -> dict[str, Any]:
    """Weekly full re-crawl: catches files that were replaced in place (revisions)."""
    return _crawl(IngestionRun.Trigger.SCHEDULE)


@shared_task(name="draws.poll_draw_day")
def poll_draw_day() -> int:
    """Every 30 minutes from 12:00 to 23:30: poll the pages of draws that are due and not yet found."""
    fetcher = crawl.make_fetcher()
    try:
        return len(crawl.poll_draw_day(fetcher))
    finally:
        fetcher.close()


@shared_task(name="draws.check_missing_draws")
def check_missing_draws() -> int:
    return crawl.check_missing_draws()


@shared_task(name="draws.check_overdue_reviews")
def check_overdue_reviews() -> int:
    return crawl.check_overdue_reviews()


@shared_task(name="draws.process_outbox")
def process_outbox() -> int:
    return crawl.process_outbox()

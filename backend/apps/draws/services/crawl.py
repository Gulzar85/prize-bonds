"""Crawl savings.gov.pk: discovery, draw-day polling, missing-draw and overdue-review checks, the outbox consumer.

Used by the Celery tasks and the ``backfill_draws`` command alike, so both run the same code paths.
"""

import datetime
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.draws import alerts
from apps.draws.ingestion.discovery import DiscoveredLink, parse_denomination_page, parse_index, select_sources
from apps.draws.ingestion.extractors import ExtractionError, extract
from apps.draws.ingestion.fetcher import Fetcher, FetcherConfig, FetchError
from apps.draws.ingestion.parser import parse
from apps.draws.ingestion.types import Severity
from apps.draws.ingestion.validators import ValidationContext, validate
from apps.draws.models import Denomination, Draw, DrawRevision, DrawSchedule, IngestionRun, OutboxEvent
from apps.draws.services import pipeline

logger = logging.getLogger(__name__)

POLL_START = datetime.time(12, 0)
POLL_END = datetime.time(23, 30)
POLL_HOURLY_DAYS = 3
MISSING_AFTER_DAYS = 3
REVIEW_OVERDUE_AFTER = datetime.timedelta(hours=24)


def make_fetcher() -> Fetcher:
    return Fetcher(
        FetcherConfig(
            user_agent=settings.DRAWS_USER_AGENT,
            allowed_hosts=tuple(settings.DRAWS_ALLOWED_HOSTS),
            min_interval=settings.DRAWS_MIN_REQUEST_INTERVAL,
            max_bytes=settings.DRAWS_MAX_FILE_BYTES,
        )
    )


@dataclass
class CrawlStats:
    pages_fetched: int = 0
    files_new: int = 0
    files_unchanged: int = 0
    files_failed: int = 0
    undated_links: int = 0
    errors: list[str] = field(default_factory=list)
    #: dry runs only: one row per file with the finding codes, nothing is written
    dry_rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class CrawlResult:
    run: IngestionRun | None
    stats: CrawlStats


def _known_pages() -> dict[str, str]:
    return {urlparse(d.source_page_url).path.rstrip("/"): d.slug for d in Denomination.objects.all()}


def dry_run_link(fetcher: Fetcher, link: DiscoveredLink, denomination: Denomination) -> dict[str, Any]:
    """Download, extract, parse and validate one file without touching the database."""
    assert link.parsed_date is not None
    row: dict[str, Any] = {"denomination": denomination.slug, "date": link.parsed_date.isoformat(), "ext": link.ext}
    fetched = fetcher.get_file(link.url, link.ext)
    if not hasattr(fetched, "content"):
        row["status"] = "unchanged"
        return row
    try:
        extracted = extract(fetched.content, link.ext)
    except ExtractionError as exc:
        row.update(status="unreadable", errors=["extraction_failed"], warnings=[], detail=str(exc))
        return row
    result = parse(extracted.text)
    findings = validate(
        result,
        ValidationContext(
            link_date=link.parsed_date,
            expected_denomination_value=denomination.value_pkr,
            number_length=denomination.number_length,
        ),
    )
    errors = sorted({f.code for f in findings if f.severity is Severity.ERROR})
    warnings = sorted({f.code for f in findings if f.severity is Severity.WARNING} | {w.code for w in result.warnings})
    row.update(status="errors" if errors else "warnings" if warnings else "clean", errors=errors, warnings=warnings)
    return row


def run_crawl(
    fetcher: Fetcher,
    trigger: str,
    *,
    slugs: list[str] | None = None,
    since_year: int | None = None,
    only_date: datetime.date | None = None,
    dry_run: bool = False,
    check_index: bool = True,
    progress: Callable[[str], None] | None = None,
) -> CrawlResult:
    stats = CrawlStats()
    run = None
    if not dry_run:
        run = IngestionRun.objects.create(trigger=trigger, started_at=timezone.now())

    denominations = Denomination.objects.filter(is_active=True)
    if slugs:
        denominations = denominations.filter(slug__in=slugs)

    if check_index:
        try:
            index_html = fetcher.get_page(settings.DRAWS_INDEX_URL)
            stats.pages_fetched += 1
            for entry in parse_index(index_html, settings.DRAWS_INDEX_URL, _known_pages()):
                if entry.slug is None:
                    alerts.raise_alert(
                        alerts.UNKNOWN_DENOMINATION,
                        "The download page lists a denomination we do not know",
                        text=entry.text,
                        url=entry.url,
                    )
        except FetchError as exc:
            stats.errors.append(f"index: {exc}")

    for denomination in denominations:
        _crawl_denomination(fetcher, denomination, stats, since_year, only_date, dry_run, progress)

    if run is not None:
        run.finished_at = timezone.now()
        run.pages_fetched = stats.pages_fetched
        run.files_new, run.files_unchanged, run.files_failed = (
            stats.files_new,
            stats.files_unchanged,
            stats.files_failed,
        )
        run.error_summary = "\n".join(stats.errors)[:4000]
        pages_wanted = denominations.count()
        if stats.pages_fetched == 0 or (stats.errors and stats.files_new + stats.files_unchanged == 0 and pages_wanted):
            run.outcome = IngestionRun.Outcome.FAILED
        elif stats.errors or stats.files_failed or stats.undated_links:
            run.outcome = IngestionRun.Outcome.PARTIAL
        else:
            run.outcome = IngestionRun.Outcome.SUCCESS
        run.save()
    return CrawlResult(run, stats)


def _crawl_denomination(
    fetcher: Fetcher,
    denomination: Denomination,
    stats: CrawlStats,
    since_year: int | None,
    only_date: datetime.date | None,
    dry_run: bool,
    progress: Callable[[str], None] | None = None,
) -> None:
    try:
        html = fetcher.get_page(denomination.source_page_url)
    except FetchError as exc:
        stats.errors.append(f"{denomination.slug}: {exc}")
        alerts.raise_alert(
            alerts.FETCH_FAILURE, str(exc), denomination=denomination.slug, url=denomination.source_page_url
        )
        return
    stats.pages_fetched += 1

    links = parse_denomination_page(html, denomination.source_page_url, denomination.slug)
    undated = [link for link in links if link.parsed_date is None]
    stats.undated_links += len(undated)
    for link in undated:
        alerts.raise_alert(
            alerts.UNKNOWN_LAYOUT,
            "A result link has no usable date, so it was skipped",
            denomination=denomination.slug,
            link_text=link.link_text,
            url=link.url,
        )

    for draw_date, link in sorted(select_sources(links).items()):
        if since_year and draw_date.year < since_year:
            continue
        if only_date and draw_date != only_date:
            continue
        try:
            if dry_run:
                stats.dry_rows.append(dry_run_link(fetcher, link, denomination))
                if progress:
                    progress(f"{denomination.slug} {draw_date}: {stats.dry_rows[-1]['status']}")
                continue
            outcome = pipeline.ingest_link(fetcher, link, denomination)
        except FetchError as exc:  # dry runs call the fetcher directly
            stats.files_failed += 1
            stats.errors.append(f"{denomination.slug} {draw_date}: {exc}")
            continue
        if progress:
            progress(f"{denomination.slug} {draw_date}: {outcome.outcome.lower()}")
        if outcome.outcome == pipeline.NEW_REVISION:
            stats.files_new += 1
        elif outcome.outcome == pipeline.UNCHANGED:
            stats.files_unchanged += 1
        else:
            stats.files_failed += 1
            stats.errors.append(f"{denomination.slug} {draw_date}: {outcome.detail}")


# --- draw-day polling ----------------------------------------


def in_polling_window(scheduled: datetime.date, now: datetime.datetime) -> bool:
    """Every 30 minutes 12:00-23:30 on the draw day, then hourly (the :00 run) for three days."""
    today = timezone.localtime(now).date() if timezone.is_aware(now) else now.date()
    clock = timezone.localtime(now).time() if timezone.is_aware(now) else now.time()
    if today == scheduled:
        return POLL_START <= clock <= POLL_END
    if scheduled < today <= scheduled + datetime.timedelta(days=POLL_HOURLY_DAYS):
        return POLL_START <= clock <= POLL_END and clock.minute < 30
    return False


def draw_found(schedule: DrawSchedule) -> bool:
    return Draw.objects.filter(
        denomination=schedule.denomination, draw_date=schedule.scheduled_date, revisions__isnull=False
    ).exists()


def poll_draw_day(fetcher: Fetcher, now: datetime.datetime | None = None) -> list[CrawlResult]:
    """Crawl the pages of denominations whose draw is due and not yet found; stops per schedule once found."""
    now = now or timezone.now()
    results = []
    for schedule in DrawSchedule.objects.select_related("denomination").filter(
        scheduled_date__gte=timezone.localdate(now) - datetime.timedelta(days=POLL_HOURLY_DAYS),
        scheduled_date__lte=timezone.localdate(now),
    ):
        if not in_polling_window(schedule.scheduled_date, now) or draw_found(schedule):
            continue
        results.append(
            run_crawl(
                fetcher,
                IngestionRun.Trigger.DRAW_DAY,
                slugs=[schedule.denomination.slug],
                only_date=schedule.scheduled_date,
                check_index=False,
            )
        )
    return results


# --- watchdogs ----------------------------------------


def check_missing_draws(now: datetime.datetime | None = None) -> int:
    """Alert once for every scheduled draw still not found three days after its date."""
    now = now or timezone.now()
    cutoff = timezone.localdate(now) - datetime.timedelta(days=MISSING_AFTER_DAYS)
    alerted = 0
    for schedule in DrawSchedule.objects.select_related("denomination").filter(
        scheduled_date__lt=cutoff, missing_alerted_at__isnull=True
    ):
        if draw_found(schedule):
            continue
        alerts.raise_alert(
            alerts.DRAW_NOT_FOUND,
            f"The {schedule.denomination} draw scheduled for {schedule.scheduled_date} has not appeared",
            denomination=schedule.denomination.slug,
            scheduled_date=schedule.scheduled_date,
        )
        schedule.missing_alerted_at = now
        schedule.save(update_fields=["missing_alerted_at", "updated_at"])
        alerted += 1
    return alerted


def check_overdue_reviews(now: datetime.datetime | None = None) -> int:
    """Alert once for every revision that has waited more than 24 hours for a decision."""
    now = now or timezone.now()
    alerted = 0
    for revision in DrawRevision.objects.select_related("draw__denomination").filter(
        status=DrawRevision.Status.NEEDS_REVIEW,
        created_at__lt=now - REVIEW_OVERDUE_AFTER,
        overdue_alerted_at__isnull=True,
    ):
        alerts.raise_alert(
            alerts.REVIEW_OVERDUE,
            f"{revision.draw} has waited more than 24 hours for review",
            denomination=revision.draw.denomination.slug,
            draw_date=revision.draw.draw_date,
            revision=revision.pk,
        )
        revision.overdue_alerted_at = now
        revision.save(update_fields=["overdue_alerted_at", "updated_at"])
        alerted += 1
    return alerted


# --- outbox ----------------------------------------


def process_outbox(batch: int = 100) -> int:
    """Phase 1 consumer: log each event and mark it processed. Phase 2's matcher replaces this."""
    processed = 0
    with transaction.atomic():
        events = list(OutboxEvent.objects.select_for_update(skip_locked=True).filter(processed_at__isnull=True)[:batch])
        for event in events:
            logger.info("outbox event %s %s", event.type, event.payload)
            event.processed_at = timezone.now()
            event.save(update_fields=["processed_at"])
            processed += 1
    return processed

"""discover -> fetch -> store raw -> extract -> parse -> validate -> persist revision (-> review -> publish).

This module owns everything up to and including "persist revision". Publication lives in :mod:`review`.
"""

import datetime
import hashlib
import logging
from dataclasses import dataclass
from itertools import batched
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.draws import alerts
from apps.draws.ingestion.discovery import DiscoveredLink
from apps.draws.ingestion.extractors import ExtractionError, extract
from apps.draws.ingestion.extractors.dispatch import SUPPORTED_EXTENSIONS
from apps.draws.ingestion.fetcher import Fetched, Fetcher, FetchError, NotModified
from apps.draws.ingestion.parser import parse
from apps.draws.ingestion.storage import raw_key, store_raw
from apps.draws.ingestion.types import Finding, ParseResult, Severity
from apps.draws.ingestion.validators import ValidationContext, validate
from apps.draws.models import Denomination, Draw, DrawRevision, PrizeTier, WinningNumber
from apps.draws.services.diff import compute_diff
from apps.draws.states import check_draw_transition, check_revision_transition

logger = logging.getLogger(__name__)

INSERT_BATCH_SIZE = 1000
NEW_REVISION, UNCHANGED, FAILED = "NEW_REVISION", "UNCHANGED", "FAILED"


@dataclass(frozen=True)
class IngestResult:
    outcome: str
    revision: DrawRevision | None = None
    detail: str = ""


# --- draws ----------------------------------------------------------------------------------------------------------


def get_or_create_draw(denomination: Denomination, draw_date: datetime.date) -> tuple[Draw, bool]:
    return Draw.objects.get_or_create(denomination=denomination, draw_date=draw_date)


def _set_draw_status(draw: Draw, target: str) -> None:
    if draw.status == target:
        return
    check_draw_transition(draw.status, target)
    draw.status = target
    draw.save(update_fields=["status", "updated_at"])


# --- ingest ---------------------------------------------------------------------------------------------------------


def ingest_link(fetcher: Fetcher, link: DiscoveredLink, denomination: Denomination) -> IngestResult:
    """Fetch one discovered file and, if it is new or changed, create and process a revision."""
    assert link.parsed_date is not None, "links without a date must be reported by the caller, not ingested"
    draw, _ = get_or_create_draw(denomination, link.parsed_date)
    latest = draw.revisions.order_by("-revision_no").first()
    etag = latest.etag if latest and latest.source_url == link.url else ""
    last_modified = latest.last_modified if latest and latest.source_url == link.url else ""
    try:
        fetched = fetcher.get_file(link.url, link.ext, etag=etag, last_modified=last_modified)
    except FetchError as exc:
        alerts.raise_alert(alerts.FETCH_FAILURE, str(exc), denomination=denomination.slug, url=link.url)
        return IngestResult(FAILED, detail=str(exc))
    if isinstance(fetched, NotModified):
        return IngestResult(UNCHANGED, latest, "not modified")
    return _create_if_new(draw, fetched, link.ext, link.url, link.link_text, uploaded_by=None)


def _create_if_new(
    draw: Draw, fetched: Fetched, ext: str, url: str, link_text: str, uploaded_by: User | None
) -> IngestResult:
    existing = draw.revisions.filter(sha256=fetched.sha256).first()
    if existing is not None:
        return IngestResult(UNCHANGED, existing, "same content already stored")
    revision = create_revision(
        draw,
        fetched.content,
        ext,
        source_url=url,
        link_text=link_text,
        etag=fetched.etag,
        last_modified=fetched.last_modified,
        uploaded_by=uploaded_by,
    )
    return IngestResult(NEW_REVISION, revision)


def create_revision(
    draw: Draw,
    content: bytes,
    ext: str,
    *,
    source_url: str = "",
    link_text: str = "",
    etag: str = "",
    last_modified: str = "",
    uploaded_by: User | None = None,
) -> DrawRevision:
    """Store the raw file, record a PENDING revision and process it. Used by crawling and manual upload alike."""
    ext = ext.lower().lstrip(".")
    sha = hashlib.sha256(content).hexdigest()
    key = store_raw(raw_key(draw.denomination.slug, draw.draw_date, sha, ext), content)
    with transaction.atomic():
        last = draw.revisions.order_by("-revision_no").values_list("revision_no", flat=True).first() or 0
        revision = DrawRevision.objects.create(
            draw=draw,
            revision_no=last + 1,
            source_url=source_url,
            link_text=link_text[:255],
            file_ext=ext,
            sha256=sha,
            size_bytes=len(content),
            storage_key=key,
            etag=etag,
            last_modified=last_modified,
            fetched_at=timezone.now(),
            uploaded_by=uploaded_by,
        )
    process_revision(revision, content)
    return revision


# --- processing -----------------------------------------------------------------------------------------------------


def _finding_dicts(findings: list[Finding]) -> list[dict[str, Any]]:
    return [f.as_dict() for f in findings]


def build_context(draw: Draw, revision: DrawRevision) -> ValidationContext:
    previous = (
        Draw.objects.filter(denomination=draw.denomination, status=Draw.Status.PUBLISHED, draw_date__lt=draw.draw_date)
        .exclude(published_revision=None)
        .order_by("-draw_date")
        .first()
    )
    previous_amounts: dict[int, int] = {}
    previous_third: int | None = None
    if previous is not None and previous.published_revision_id:
        for tier in PrizeTier.objects.filter(revision_id=previous.published_revision_id):
            previous_amounts[tier.rank] = tier.amount_pkr
            if tier.rank == 3:
                previous_third = tier.parsed_count
    return ValidationContext(
        link_date=draw.draw_date,
        expected_denomination_value=draw.denomination.value_pkr,
        number_length=draw.denomination.number_length,
        previous_draw_number=previous.draw_number if previous else None,
        previous_amounts=previous_amounts,
        previous_third_count=previous_third,
    )


def _numbers_by_rank(revision: DrawRevision) -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for rank, number in WinningNumber.objects.filter(revision=revision).values_list("tier__rank", "number"):
        out.setdefault(rank, set()).add(number)
    return out


def _previous_revision(revision: DrawRevision) -> DrawRevision | None:
    """What this revision should be compared with: what is published, else the newest earlier usable revision."""
    draw = revision.draw
    if draw.published_revision_id and draw.published_revision_id != revision.pk:
        return DrawRevision.objects.get(pk=draw.published_revision_id)
    return (
        draw.revisions.filter(revision_no__lt=revision.revision_no)
        .exclude(status__in=[DrawRevision.Status.PARSE_FAILED, DrawRevision.Status.REJECTED])
        .filter(tiers__isnull=False)
        .distinct()
        .order_by("-revision_no")
        .first()
    )


def _draw_conflicts(draw: Draw, result: ParseResult) -> list[Finding]:
    findings: list[Finding] = []
    if result.draw_number is None:
        return findings
    if draw.draw_number is not None and draw.draw_number != result.draw_number:
        findings.append(
            Finding(
                "draw_number_mismatch",
                Severity.ERROR,
                f"File says draw {result.draw_number}, this draw is recorded as {draw.draw_number}",
                {"file": result.draw_number, "recorded": draw.draw_number},
            )
        )
    clash = (
        Draw.objects.filter(denomination=draw.denomination, draw_number=result.draw_number).exclude(pk=draw.pk).first()
    )
    if clash is not None:
        findings.append(
            Finding(
                "draw_number_conflict",
                Severity.ERROR,
                f"Draw number {result.draw_number} already belongs to the draw of {clash.draw_date}",
                {"draw_number": result.draw_number, "other_draw_date": clash.draw_date.isoformat()},
            )
        )
    return findings


def _fail(revision: DrawRevision, code: str, message: str) -> None:
    error = Finding(code, Severity.ERROR, message)
    check_revision_transition(revision.status, DrawRevision.Status.PARSE_FAILED)
    revision.status = DrawRevision.Status.PARSE_FAILED
    revision.parse_errors = _finding_dicts([error])
    revision.save(update_fields=["status", "parse_errors", "updated_at"])
    draw = revision.draw
    if draw.status in (Draw.Status.DISCOVERED, Draw.Status.IN_REVIEW) and not draw.published_revision_id:
        _set_draw_status(draw, Draw.Status.FAILED)
    alerts.raise_alert(
        alerts.PARSE_FAILURE,
        message,
        denomination=draw.denomination.slug,
        draw_date=draw.draw_date,
        revision=revision.pk,
        error_code=code,
    )


def process_revision(revision: DrawRevision, content: bytes) -> DrawRevision:
    """Extract, parse and validate a PENDING revision; persist tiers and numbers; move it to review."""
    if revision.status != DrawRevision.Status.PENDING:
        raise ValueError("Only PENDING revisions can be processed")
    draw = revision.draw

    try:
        extracted = extract(content, revision.file_ext)
    except ExtractionError as exc:
        _fail(revision, "extraction_failed", f"Could not read the file: {exc}")
        return revision

    result = parse(extracted.text)
    ctx = build_context(draw, revision)
    previous = _previous_revision(revision)
    old_numbers = _numbers_by_rank(previous) if previous else {}
    new_numbers = {t.rank: set(t.numbers) for t in result.tiers}
    diff = compute_diff(
        old_numbers,
        new_numbers,
        previous.parsed_header if previous else {},
        result.header_dict(),
        {t.rank: t.amount_pkr for t in PrizeTier.objects.filter(revision=previous)} if previous else None,
        {t.rank: t.amount_pkr for t in result.tiers if t.amount_pkr is not None},
    )
    if previous is not None:
        ctx = ValidationContext(**{**ctx.__dict__, "diff_ratio": diff["ratio"]})

    findings = validate(result, ctx) + _draw_conflicts(draw, result)
    extraction_warnings = [Finding("extraction_warning", Severity.WARNING, w) for w in extracted.warnings]
    warnings = extraction_warnings + list(result.warnings) + [f for f in findings if f.severity is Severity.WARNING]
    errors = [f for f in findings if f.severity is Severity.ERROR]

    with transaction.atomic():
        _persist_tiers_and_numbers(revision, result)
        revision.extraction_method = extracted.method
        revision.parsed_header = result.header_dict()
        revision.parse_warnings = _finding_dicts(warnings)
        revision.parse_errors = _finding_dicts(errors)
        revision.diff_from_previous = diff if previous else {}
        check_revision_transition(revision.status, DrawRevision.Status.NEEDS_REVIEW)
        revision.status = DrawRevision.Status.NEEDS_REVIEW
        revision.save(
            update_fields=[
                "extraction_method",
                "parsed_header",
                "parse_warnings",
                "parse_errors",
                "diff_from_previous",
                "status",
                "updated_at",
            ]
        )
        _sync_draw(draw, result, errors)
        if draw.status != Draw.Status.PUBLISHED:
            _set_draw_status(draw, Draw.Status.IN_REVIEW)

    if draw.status == Draw.Status.PUBLISHED:
        alerts.raise_alert(
            alerts.REVISION_DETECTED,
            f"A new file appeared for the published draw of {draw.draw_date}",
            denomination=draw.denomination.slug,
            draw_date=draw.draw_date,
            revision=revision.pk,
            changed_numbers=diff["changed_numbers"],
        )
    if any(w.code == "unrecognised_lines" for w in result.warnings) or not result.tiers:
        alerts.raise_alert(
            alerts.UNKNOWN_LAYOUT,
            "The file contains lines or sections the parser does not understand",
            denomination=draw.denomination.slug,
            draw_date=draw.draw_date,
            revision=revision.pk,
        )
    return revision


def _persist_tiers_and_numbers(revision: DrawRevision, result: ParseResult) -> None:
    draw = revision.draw
    seen: set[str] = set()
    for parsed in result.tiers:
        unique = [n for n in dict.fromkeys(parsed.numbers) if n not in seen]  # duplicates are reported, not stored
        tier = PrizeTier.objects.create(
            revision=revision,
            rank=parsed.rank,
            amount_pkr=parsed.amount_pkr or 0,
            announced_count=parsed.announced_count,
            parsed_count=len(parsed.numbers),
        )
        seen.update(unique)
        for chunk in batched(unique, INSERT_BATCH_SIZE, strict=False):
            WinningNumber.objects.bulk_create(
                [
                    WinningNumber(
                        revision=revision, tier=tier, draw=draw, denomination=draw.denomination, number=number
                    )
                    for number in chunk
                ]
            )


def _sync_draw(draw: Draw, result: ParseResult, errors: list[Finding]) -> None:
    """Copy header facts onto the draw without ever overwriting a known value or breaking uniqueness."""
    blocked = {e.code for e in errors}
    changed: list[str] = []
    if draw.draw_number is None and result.draw_number is not None and "draw_number_conflict" not in blocked:
        draw.draw_number = result.draw_number
        changed.append("draw_number")
    if not draw.city and result.city:
        draw.city = result.city
        changed.append("city")
    if changed:
        draw.save(update_fields=[*changed, "updated_at"])
        logger.info("draw %s updated from header: %s", draw.pk, changed)


# --- manual upload --------------------------------------------------------------------------------------------------


class UploadRejected(Exception):
    pass


def upload_revision(
    denomination: Denomination, draw_date: datetime.date, content: bytes, filename: str, user: User, max_bytes: int
) -> DrawRevision:
    """Manual upload: the same pipeline as crawling, attributed to the uploader (for the four-eyes rule)."""
    from apps.draws.rules import can_upload

    if not can_upload(user):
        raise UploadRejected("Only data operators with MFA enabled may upload results")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SUPPORTED_EXTENSIONS:
        raise UploadRejected(f"Unsupported file type: .{ext}")
    if not content or len(content) > max_bytes:
        raise UploadRejected("File is empty or larger than the allowed size")
    draw, _ = get_or_create_draw(denomination, draw_date)
    if draw.revisions.filter(sha256=hashlib.sha256(content).hexdigest()).exists():
        raise UploadRejected("This exact file has already been uploaded for the draw")
    return create_revision(draw, content, ext, link_text=f"manual upload: {filename}", uploaded_by=user)

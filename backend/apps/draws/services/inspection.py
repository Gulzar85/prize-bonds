"""Everything the review screen shows about one revision: header, counts, findings, source excerpts, samples, diff."""

import re
from dataclasses import dataclass
from typing import Any

from apps.draws.ingestion.extractors import ExtractionError, extract
from apps.draws.ingestion.storage import read_raw
from apps.draws.models import DrawRevision

TIER_HEADING = re.compile(r"\b(?:1st|first|2nd|second|3rd|third)\s+p+ri[cz]e|\d[\d,]*\s*Prize\(?s?\)?\s+of\b", re.I)
EXCERPT_RADIUS = 2
SAMPLE_SIZE = 20


@dataclass(frozen=True)
class TierRow:
    rank: int
    amount_pkr: int
    announced: int | None
    parsed: int
    matches: bool | None  # None when nothing was announced


@dataclass(frozen=True)
class ReviewContext:
    revision: DrawRevision
    header: dict[str, Any]
    tiers: list[TierRow]
    errors: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    excerpts: list[dict[str, Any]]
    samples: list[dict[str, Any]]
    diff: dict[str, Any]
    source_unavailable: str = ""


def _excerpts(lines: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if TIER_HEADING.search(line):
            start = max(0, index - EXCERPT_RADIUS)
            end = min(len(lines), index + EXCERPT_RADIUS + 1)
            out.append({"line": index + 1, "text": "\n".join(f"{n + 1:>5}  {lines[n]}" for n in range(start, end))})
    return out


def _samples(revision: DrawRevision, lines: list[str]) -> list[dict[str, Any]]:
    """Up to 20 parsed numbers, spread over the tiers, each next to the source line it was read from."""
    from apps.draws.models import WinningNumber

    numbers = list(
        WinningNumber.objects.filter(revision=revision)
        .order_by("tier__rank", "number")
        .values_list("number", "tier__rank")
    )
    if not numbers:
        return []
    step = max(1, len(numbers) // SAMPLE_SIZE)
    picked = numbers[::step][:SAMPLE_SIZE]
    out = []
    for number, rank in picked:
        source = next(
            (f"{n + 1:>5}  {text}" for n, text in enumerate(lines) if number in text), "(not found in the text)"
        )
        out.append({"number": number, "rank": rank, "source": source})
    return out


def build_review_context(revision: DrawRevision) -> ReviewContext:
    tiers = [
        TierRow(
            rank=t.rank,
            amount_pkr=t.amount_pkr,
            announced=t.announced_count,
            parsed=t.parsed_count,
            matches=None if t.announced_count is None else t.announced_count == t.parsed_count,
        )
        for t in revision.tiers.order_by("rank")
    ]
    lines: list[str] = []
    unavailable = ""
    try:
        lines = extract(read_raw(revision.storage_key), revision.file_ext).text.split("\n")
    except (ExtractionError, FileNotFoundError, OSError) as exc:
        unavailable = f"Source text could not be re-read: {exc}"
    return ReviewContext(
        revision=revision,
        header=revision.parsed_header,
        tiers=tiers,
        errors=list(revision.parse_errors),
        warnings=list(revision.parse_warnings),
        excerpts=_excerpts(lines),
        samples=_samples(revision, lines),
        diff=revision.diff_from_previous,
        source_unavailable=unavailable,
    )

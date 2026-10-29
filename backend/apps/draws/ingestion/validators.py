"""Validate a parse result against what is known about the draw. Pure functions, no Django imports.

Any ``ERROR`` finding blocks publication until a reviewer overrides it with a written note. Warnings are shown to the
reviewer but do not block. Findings are structured so the review screen can group and explain them.
"""

import datetime
import re
from collections import Counter
from dataclasses import dataclass, field

from apps.draws.ingestion.types import Finding, ParseResult, Severity

#: A revision whose numbers differ from the previous one by more than this share gets a warning.
LARGE_DIFF_RATIO = 0.01
_FILLER = re.compile(r"[Xx*]+")


@dataclass(frozen=True)
class ValidationContext:
    """Facts from outside the file. Anything unknown is ``None`` and the matching check is skipped."""

    link_date: datetime.date | None = None
    expected_denomination_value: int | None = None
    number_length: int = 6
    previous_draw_number: int | None = None
    #: rank -> amount of the previous published draw of this denomination.
    previous_amounts: dict[int, int] = field(default_factory=dict)
    #: Third-prize count of the previous published draw of this denomination.
    previous_third_count: int | None = None
    #: Share of numbers that changed against the previous revision of the same draw.
    diff_ratio: float | None = None


def _error(code: str, message: str, **context: object) -> Finding:
    return Finding(code, Severity.ERROR, message, dict(context))


def _warning(code: str, message: str, **context: object) -> Finding:
    return Finding(code, Severity.WARNING, message, dict(context))


def validate(result: ParseResult, ctx: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    findings += _check_header(result, ctx)
    findings += _check_tiers(result)
    findings += _check_numbers(result, ctx)
    findings += _check_counts(result, ctx)
    findings += _check_amounts(result, ctx)
    findings += _check_grid_order(result)
    if ctx.diff_ratio is not None and ctx.diff_ratio > LARGE_DIFF_RATIO:
        findings.append(
            _warning(
                "revision_diff_large",
                f"{ctx.diff_ratio:.1%} of numbers differ from the previous revision (limit {LARGE_DIFF_RATIO:.0%})",
                ratio=ctx.diff_ratio,
            )
        )
    return findings


def _check_header(result: ParseResult, ctx: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    if result.draw_date and ctx.link_date and result.draw_date != ctx.link_date:
        findings.append(
            _error(
                "header_date_mismatch",
                f"File says {result.draw_date}, the link says {ctx.link_date}",
                header_date=result.draw_date.isoformat(),
                link_date=ctx.link_date.isoformat(),
            )
        )
    if result.denomination_value is not None and ctx.expected_denomination_value is not None:
        if result.denomination_value != ctx.expected_denomination_value:
            findings.append(
                _error(
                    "denomination_mismatch",
                    f"File is for Rs {result.denomination_value}, "
                    f"it came from the Rs {ctx.expected_denomination_value} page",
                    header=result.denomination_value,
                    page=ctx.expected_denomination_value,
                )
            )
    if (
        result.draw_number is not None
        and ctx.previous_draw_number is not None
        and result.draw_number != ctx.previous_draw_number + 1
    ):
        findings.append(
            _warning(
                "draw_number_not_sequential",
                f"Draw {result.draw_number} does not follow the last published draw {ctx.previous_draw_number}",
                draw_number=result.draw_number,
                previous=ctx.previous_draw_number,
            )
        )
    return findings


def _check_tiers(result: ParseResult) -> list[Finding]:
    findings: list[Finding] = []
    for rank in (1, 2, 3):
        tier = result.tier(rank)
        if tier is None or not tier.numbers:
            findings.append(_error("tier_missing", f"Prize tier {rank} has no numbers", rank=rank))
    return findings


def _check_numbers(result: ParseResult, ctx: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    owner: dict[str, int] = {}
    duplicates: list[str] = []
    cross_tier: list[str] = []
    wrong_length: list[dict[str, object]] = []
    for tier in result.tiers:
        for number in tier.numbers:
            if len(number) != ctx.number_length:
                wrong_length.append({"rank": tier.rank, "number": number})
            if number in owner:
                (cross_tier if owner[number] != tier.rank else duplicates).append(number)
            else:
                owner[number] = tier.rank
    if wrong_length:
        findings.append(
            _error(
                "wrong_digit_length",
                f"{len(wrong_length)} number(s) are not {ctx.number_length} digits long",
                expected=ctx.number_length,
                numbers=wrong_length[:20],
                total=len(wrong_length),
            )
        )
    if cross_tier:
        findings.append(
            _error(
                "number_in_two_tiers",
                f"{len(cross_tier)} number(s) appear in more than one tier",
                numbers=sorted(set(cross_tier))[:20],
            )
        )
    if duplicates:
        findings.append(
            _error(
                "duplicate_number",
                f"{len(set(duplicates))} number(s) appear more than once in the same tier",
                numbers=sorted(set(duplicates))[:20],
            )
        )
    return findings


def _check_counts(result: ParseResult, ctx: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    parsed = {t.rank: len(t.numbers) for t in result.tiers}
    total = sum(parsed.values())

    for tier in result.tiers:
        got, announced = len(tier.numbers), tier.announced_count
        if announced is None:
            if tier.rank == 3:
                findings.append(_warning("announced_count_missing", "File announces no third-prize count", parsed=got))
            continue
        if announced == got:
            continue
        if tier.rank == 3 and announced == total:
            findings.append(
                _warning(
                    "announced_count_is_total",
                    f"Announced {announced} equals all tiers together ({total}), not the third tier alone ({got})",
                    announced=announced,
                    third=got,
                    total=total,
                )
            )
            continue
        findings.append(
            _error(
                "announced_count_mismatch",
                f"Tier {tier.rank}: announced {announced}, parsed {got}",
                rank=tier.rank,
                announced=announced,
                parsed=got,
            )
        )

    if result.announced_total is not None and result.announced_total != total:
        findings.append(
            _error(
                "announced_total_mismatch",
                f"Summary announces {result.announced_total} numbers in total, parsed {total}",
                announced=result.announced_total,
                parsed=total,
            )
        )

    third = parsed.get(3)
    if third and ctx.previous_third_count and third != ctx.previous_third_count:
        findings.append(
            _warning(
                "third_count_differs_from_previous",
                f"{third} third-prize numbers; the previous published draw had {ctx.previous_third_count}",
                parsed=third,
                previous=ctx.previous_third_count,
            )
        )
    return findings


def _check_amounts(result: ParseResult, ctx: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    for tier in result.tiers:
        if tier.amount_pkr is None or tier.amount_pkr <= 0:
            findings.append(
                _error("amount_not_positive", f"Tier {tier.rank} has no positive prize amount", rank=tier.rank)
            )
            continue
        before = ctx.previous_amounts.get(tier.rank)
        if before is not None and before != tier.amount_pkr:
            findings.append(
                _warning(
                    "amount_changed",
                    f"Tier {tier.rank} amount Rs {tier.amount_pkr} differs from the previous draw's Rs {before}",
                    rank=tier.rank,
                    amount=tier.amount_pkr,
                    previous=before,
                )
            )
    return findings


def _check_grid_order(result: ParseResult) -> list[Finding]:
    """The third-prize grid is sorted ascending down each column; report columns that are not."""
    rows = result.grid_rows
    if not rows:
        return []
    columns = max(len(row) for row in rows)
    unsorted: list[int] = []
    for column in range(columns):
        values = [row[column] for row in rows if len(row) > column and not _FILLER.fullmatch(row[column])]
        if any(a >= b for a, b in zip(values, values[1:], strict=False)):
            unsorted.append(column + 1)
    if not unsorted:
        return []
    return [_warning("grid_not_sorted", f"Grid columns {unsorted} are not ascending", columns=unsorted)]


def has_errors(findings: list[Finding]) -> bool:
    return any(f.severity is Severity.ERROR for f in findings)


def summarise(findings: list[Finding]) -> Counter[str]:
    return Counter(f.code for f in findings)

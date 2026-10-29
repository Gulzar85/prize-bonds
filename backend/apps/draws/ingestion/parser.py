"""Parse the text of a National Savings draw result. Pure function, no Django imports.

The parser never raises on soft problems and never guesses silently: every assumption it makes becomes a warning
on the result. Numbers are kept exactly as printed (digits only, never padded); length checks belong to validators.
"""

import datetime
import re

from apps.draws.ingestion.types import Finding, ParsedTier, ParseResult, Severity

# --- header ---------------------------------------------------------------------------------------------------------

_MONTHS = {
    name: number
    for number, name in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ],
        start=1,
    )
}
_ORDINAL_DRAW = re.compile(r"(\d{1,3})\s*(?:st|nd|rd|th)\s*draw\b", re.I)
_DRAW_NO = re.compile(r"draw\s*no\.?\s*:?\s*(\d{1,3})", re.I)
_NUMERIC_DATE = re.compile(r"(?<!\d)(\d{1,2})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{4})(?!\d)")
_TEXT_DATE = re.compile(
    r"(?<!\d)(\d{1,2})\s*(?:st|nd|rd|th)?[\s,]*(" + "|".join(_MONTHS) + r")\s*[,.]?\s*(\d{4})(?!\d)", re.I
)
_HELD = re.compile(r"held\s+(?:on|at)", re.I)
_HELD_BEFORE_DATE = re.compile(r"held\b[^.\n]{0,25}$", re.I)
_CITY = re.compile(
    r"\bat\s+(?:SBP\s*)?(?:\(?\s*BSC\s*\)?\s*)?([A-Za-z][A-Za-z ]*?)(?=\s+on\b|\s*\d|\s*\(|\s+held\b|\s*$)",
    re.I | re.M,
)
_DENOMINATION = re.compile(r"Rs\.?\s*(?:premium\s*)?(\d[\d, ]*\d|\d)\s*/-", re.I)

# --- tiers ----------------------------------------------------------------------------------------------------------

_FIRST = re.compile(r"\b(?:1st|first)\s+p+ri[cz]e", re.I)  # the source has "Third Price" and "Pprize" typos
_SECOND = re.compile(r"\b(?:2nd|second)\s+p+ri[cz]e", re.I)
_THIRD = re.compile(r"\b(?:3rd|third)\s+p+ri[cz]e", re.I)
#: "(2400 Prizes of Rs.1250/- Each)", "2394 Prize(s) of 1250/- Each", "Third Prize of 1696 Prizes of Rs.9,300/- Each"
_COUNT_OF = re.compile(r"(\d[\d,]*)\s*Prize\(?s?\)?\s+of\s+(?:Rs\.?\s*)?(\d[\d, ]*\d|\d)", re.I)
_AMOUNT = re.compile(r"Rs\.?\s*(?:Rs\.?\s*)?(\d[\d, ]*\d|\d)", re.I)
#: "01 Prize:", "05 Prizes", "(03 Prizes)"; "Prizes of" is the third-tier form handled above.
_COUNT = re.compile(r"\(?\b(\d{1,5})\s*Prizes?\b(?!\s*of\b)", re.I)

#: Official "Part-I" summary lines (PDF/DOCX): "165 Prizes of Rs.750,000/- each 01 Prize in each series".
_SUMMARY_TIER = re.compile(
    r"(\d[\d,]*)\s*Prizes?\s*of\s*Rs\.?\s*(\d[\d, ]*\d|\d)\s*/?-?\s*each"
    r"\s*\(?\s*(\d[\d,]*)\s*Prizes?\s*in\s*each\s*series",
    re.I,
)
_SUMMARY_TOTAL = re.compile(r"(\d[\d,]*)\s*Total\s*Prizes\s*\(?\s*(\d[\d,]*)\s*Prizes?\s*in\s*each\s*series", re.I)

_CELL = re.compile(r"\d{4,8}|[Xx*]{3,8}")
_FILLER = re.compile(r"[Xx*]{3,8}")
#: Lines that carry no draw data: blank/rules, page and part markers, series, and the signature block.
_NOISE = re.compile(
    r"^(?:[-=_*\s|]*"
    r"|.*\bpage\b.*"
    r"|\s*part\s*-?\s*[ivx]+.*"
    r"|\s*series\s*:.*"
    r"|\s*dated\s*:.*"
    r"|\s*state\s+bank\s+of\s+pakistan\s*"
    r"|.*\b(?:manager|secretary)\b.*"
    r"|\s*prize\s+bond\s+unit\b.*"
    r"|(?:\s*\([A-Za-z .]+\)\s*)+)$",
    re.I,
)

_MAX_UNRECOGNISED_REPORTED = 8


def _warn(code: str, message: str, **context: object) -> Finding:
    return Finding(code, Severity.WARNING, message, dict(context))


def _to_int(text: str) -> int:
    return int(re.sub(r"[^\d]", "", text))


def _safe_date(year: int, month: int, day: int) -> datetime.date | None:
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _find_dates(text: str) -> list[tuple[int, datetime.date | None, str]]:
    """Every date in the text as (position, date or None if impossible, raw text)."""
    found: list[tuple[int, datetime.date | None, str]] = []
    for match in _NUMERIC_DATE.finditer(text):
        day, month, year = (int(g) for g in match.groups())
        found.append((match.start(), _safe_date(year, month, day), match[0]))
    for match in _TEXT_DATE.finditer(text):
        found.append((match.start(), _safe_date(int(match[3]), _MONTHS[match[2].lower()], int(match[1])), match[0]))
    return sorted(found, key=lambda item: item[0])


def _parse_header(lines: list[str]) -> tuple[int | None, datetime.date | None, str | None, int | None, list[Finding]]:
    text = "\n".join(lines)
    findings: list[Finding] = []

    draw_number: int | None = None
    if match := _ORDINAL_DRAW.search(text) or _DRAW_NO.search(text):
        draw_number = int(match[1])
    else:
        findings.append(_warn("header_no_draw_number", "Header has no draw number"))

    draw_date: datetime.date | None = None
    dates = _find_dates(text)
    if dates:
        # Prefer the date that follows "held ..."; other dates are cut-offs and approval dates.
        held = [d for d in dates if _HELD_BEFORE_DATE.search(text[max(0, d[0] - 40) : d[0]])]
        chosen = (held or dates)[0]
        draw_date = chosen[1]
        if draw_date is None:
            findings.append(_warn("header_invalid_date", "Header date is not a real date", text=chosen[2]))
        if not held and len({d[1] for d in dates}) > 1:
            findings.append(
                _warn(
                    "header_multiple_dates",
                    "Header contains several dates and none follows 'held'; the first was used",
                    dates=[d[2] for d in dates],
                )
            )
    else:
        findings.append(_warn("header_no_date", "Header has no date"))

    city: str | None = None
    if match := _CITY.search(text):
        city = match[1].strip().title() or None
    if city is None:
        findings.append(_warn("header_no_city", "Header has no city"))

    denomination: int | None = None
    if match := _DENOMINATION.search(text):
        denomination = _to_int(match[1])
    else:
        findings.append(_warn("header_no_denomination", "Header has no denomination value"))
    return draw_number, draw_date, city, denomination, findings


def parse(text: str) -> ParseResult:
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]

    header_lines: list[str] = []
    tier_numbers: dict[int, list[str]] = {1: [], 2: [], 3: []}
    amounts: dict[int, int | None] = {}
    counts: dict[int, int | None] = {}
    summary_counts: dict[int, int] = {}  # amount -> prizes per series, from the "Part-I" summary
    announced_total: int | None = None
    fillers = 0
    grid_cells = 0
    grid_rows: list[tuple[str, ...]] = []
    seen_ranks: list[int] = []
    unrecognised: list[tuple[int, str]] = []
    current: int | None = None

    for line_no, line in enumerate(lines, start=1):
        cells = re.sub(r"[|\t]+", " ", line).split()
        is_cell_row = bool(cells) and all(_CELL.fullmatch(c) for c in cells)

        if summary := _SUMMARY_TIER.search(line):
            summary_counts[_to_int(summary[2])] = _to_int(summary[3])
            continue
        if total := _SUMMARY_TOTAL.search(line):
            announced_total = _to_int(total[2])
            continue

        # Third tier: a "Third Prize" heading or an "N Prizes of Rs.X" count line.
        count_of = _COUNT_OF.search(line)
        heading_rank = (
            3
            if (_THIRD.search(line) or count_of)
            else 2
            if _SECOND.search(line)
            else 1
            if _FIRST.search(line)
            else None
        )
        if is_cell_row:
            heading_rank = None

        if current is None and heading_rank is None:
            header_lines.append(line)
            continue

        if heading_rank is not None:
            current = heading_rank
            if heading_rank not in seen_ranks:
                seen_ranks.append(heading_rank)
            stripped = line
            if count_of:
                counts[3] = _to_int(count_of[1])
                amounts[3] = _to_int(count_of[2])
                stripped = line.replace(count_of[0], " ")
            else:
                if amount := _AMOUNT.search(line):
                    amounts[heading_rank] = _to_int(amount[1])
                stripped = _AMOUNT.sub(" ", line)
            if heading_rank != 3 or not count_of:
                if count := _COUNT.search(stripped):
                    counts[heading_rank] = int(count[1])
                    stripped = stripped.replace(count[0], " ")
            if heading_rank != 3:
                tier_numbers[heading_rank].extend(re.findall(r"(?<![\w,.])\d{4,8}(?![\w,])", stripped))
            continue

        assert current is not None  # header lines were consumed above

        # A line without a digit cannot carry a number, amount or count (signature blocks, city names, "Continued").
        if not any(ch.isdigit() for ch in line) or _NOISE.match(line):
            continue

        # Some files put the header after the tier headings, or repeat it on a later page.
        if (_ORDINAL_DRAW.search(line) or _DRAW_NO.search(line) or _HELD.search(line)) and not is_cell_row:
            header_lines.append(line)
            continue

        if is_cell_row:
            for cell in cells:
                if _FILLER.fullmatch(cell):
                    fillers += 1
                else:
                    tier_numbers[current].append(cell)
                if current == 3:
                    grid_cells += 1
            if current == 3:
                grid_rows.append(tuple(cells))
            continue

        # "01 Prize:   516806" / "05 Prizes  1 2 3": a count prefix followed by numbers.
        if count := _COUNT.search(line):
            counts[current] = int(count[1])
            rest_cells = re.sub(r"[|\t:]+", " ", line.replace(count[0], " ")).split()
            if rest_cells and all(_CELL.fullmatch(c) for c in rest_cells):
                tier_numbers[current].extend(c for c in rest_cells if not _FILLER.fullmatch(c))
                continue

        unrecognised.append((line_no, line[:100]))

    findings: list[Finding] = []
    if unrecognised:
        findings.append(
            _warn(
                "unrecognised_lines",
                f"{len(unrecognised)} line(s) after the header were not understood",
                lines=[{"line": n, "text": t} for n, t in unrecognised[:_MAX_UNRECOGNISED_REPORTED]],
                total=len(unrecognised),
            )
        )

    draw_number, draw_date, city, denomination, header_findings = _parse_header(header_lines)

    tiers: list[ParsedTier] = []
    for rank in (1, 2, 3):
        if rank not in seen_ranks:
            continue
        announced = counts.get(rank)
        amount = amounts.get(rank)
        if announced is None and amount is not None and amount in summary_counts:
            announced = summary_counts[amount]
        tiers.append(
            ParsedTier(
                rank=rank,
                amount_pkr=amount,
                announced_count=announced,
                numbers=tuple(tier_numbers[rank]),
                filler_count=fillers if rank == 3 else 0,
            )
        )
    return ParseResult(
        header_text=" ".join(h for h in header_lines if h)[:300],
        draw_number=draw_number,
        draw_date=draw_date,
        city=city,
        denomination_value=denomination,
        tiers=tuple(tiers),
        grid_cells=grid_cells,
        announced_total=announced_total,
        grid_rows=tuple(grid_rows),
        warnings=tuple(header_findings + findings),
    )

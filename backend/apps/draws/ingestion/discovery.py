"""Find draw result links on savings.gov.pk pages. Takes HTML text, makes no requests, no Django imports.

The page layout is WordPress/Elementor: one ``<h2>`` per year, then one ``<h2>`` per draw with the link inside.
Parsing is selector-light on purpose: it takes every anchor that points into ``wp-content/uploads`` and relies on the
most recent four-digit ``<h2>``/``<h3>`` heading only as a cross-check, never as the source of the date.
"""

import datetime
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

#: Link text normally starts with the draw date; suffixes like " (pdf)" or "  (Txt File)" name the file format.
_TEXT_DATE = re.compile(r"^\s*(\d{1,2})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{4})")
#: File names such as 100_170826.txt, 1500_17082026.pdf, 750_15102026-1.txt carry the draw date as ddmmyy[yy].
_FILENAME_DATE = re.compile(r"_(\d{2})(\d{2})(\d{4}|\d{2})(?!\d)")
_YEAR_HEADING = re.compile(r"^(?:19|20)\d{2}$")

#: Preferred source when one draw has several files (clean text beats scans).
FORMAT_PREFERENCE = ("txt", "docx", "doc", "pdf")


@dataclass(frozen=True)
class DiscoveredLink:
    denomination_slug: str
    link_text: str
    parsed_date: datetime.date | None
    date_source: str  # "text", "filename" or "none"
    url: str
    ext: str
    year_heading: str | None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class IndexEntry:
    text: str
    url: str
    slug: str | None  # None for a denomination page we do not know


def _safe_date(year: int, month: int, day: int) -> datetime.date | None:
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _date_from_text(text: str) -> datetime.date | None:
    if match := _TEXT_DATE.match(text):
        day, month, year = (int(g) for g in match.groups())
        return _safe_date(year, month, day)
    return None


def _date_from_filename(filename: str) -> datetime.date | None:
    if match := _FILENAME_DATE.search(filename):
        day, month, year = int(match[1]), int(match[2]), match[3]
        return _safe_date(int(year) if len(year) == 4 else 2000 + int(year), month, day)
    return None


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def parse_index(html: str, base_url: str, known_pages: dict[str, str]) -> list[IndexEntry]:
    """Denomination page links from the "Download Draws" page.

    ``known_pages`` maps a page URL path (``/rs-200-prize-bond-draw``) to a denomination slug. Pages that look like
    draw lists but are not in the map come back with ``slug=None`` so the caller can alert; none is auto-created.
    """
    entries: dict[str, IndexEntry] = {}
    for anchor in _soup(html).find_all("a", href=True):
        text = anchor.get_text(" ", strip=True)
        if not re.search(r"draw\s*list", text, re.I):
            continue
        url = urljoin(base_url, str(anchor["href"]))
        path = urlparse(url).path.rstrip("/")
        entries.setdefault(url, IndexEntry(text=text, url=url, slug=known_pages.get(path)))
    return list(entries.values())


def parse_denomination_page(html: str, page_url: str, denomination_slug: str) -> list[DiscoveredLink]:
    """Every result file linked from one denomination page, in page order."""
    links: list[DiscoveredLink] = []
    year_heading: str | None = None
    soup = _soup(html)
    root = soup.find("main") or soup.body or soup
    for element in root.descendants:
        name = getattr(element, "name", None)
        if name in ("h1", "h2", "h3", "h4"):
            heading = element.get_text(" ", strip=True)
            if _YEAR_HEADING.match(heading):
                year_heading = heading
        elif name == "a" and isinstance(element, Tag):
            href = str(element.get("href", ""))
            if "wp-content/uploads" not in href:
                continue
            url = urljoin(page_url, href)
            text = element.get_text(" ", strip=True)
            filename = urlparse(url).path.rsplit("/", 1)[-1]
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            notes: list[str] = []

            parsed = _date_from_text(text)
            source = "text"
            if parsed is None:
                parsed = _date_from_filename(filename)
                source = "filename" if parsed else "none"
                notes.append("link text has no date" + ("; date taken from the file name" if parsed else ""))
            if parsed and year_heading and str(parsed.year) != year_heading:
                notes.append(f"date year {parsed.year} differs from the page heading {year_heading}")
            links.append(
                DiscoveredLink(
                    denomination_slug=denomination_slug,
                    link_text=text,
                    parsed_date=parsed,
                    date_source=source,
                    url=url,
                    ext=ext,
                    year_heading=year_heading,
                    notes=tuple(notes),
                )
            )
    return links


def select_sources(links: list[DiscoveredLink]) -> dict[datetime.date, DiscoveredLink]:
    """One preferred file per draw date. Links without a usable date are left out (the caller reports them)."""
    chosen: dict[datetime.date, DiscoveredLink] = {}
    for link in links:
        if link.parsed_date is None:
            continue
        current = chosen.get(link.parsed_date)
        if current is None or _rank(link) < _rank(current):
            chosen[link.parsed_date] = link
    return chosen


def _rank(link: DiscoveredLink) -> int:
    return FORMAT_PREFERENCE.index(link.ext) if link.ext in FORMAT_PREFERENCE else len(FORMAT_PREFERENCE)

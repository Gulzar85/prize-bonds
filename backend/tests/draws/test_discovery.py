import datetime
from pathlib import Path

import pytest

from apps.draws.ingestion.discovery import (
    DiscoveredLink,
    parse_denomination_page,
    parse_index,
    select_sources,
)

HTML = Path(__file__).resolve().parent.parent / "fixtures" / "draws_html"
BASE = "https://savings.gov.pk/"
KNOWN = {
    "/rs-100-prize-bond-draw": "rs-100",
    "/rs-200-prize-bond-draw": "rs-200",
    "/rs-750-prize-bond-draw": "rs-750",
    "/rs-1500-prize-bond-draw": "rs-1500",
    "/premium-prize-bond-rs-25000": "premium-25000",
    "/premium-prize-bond-rs-40000": "premium-40000",
}
PAGES = {
    "rs-100": "rs-100-prize-bond-draw",
    "rs-200": "rs-200-prize-bond-draw",
    "rs-750": "rs-750-prize-bond-draw",
    "rs-1500": "rs-1500-prize-bond-draw",
    "premium-25000": "premium-prize-bond-rs-25000",
    "premium-40000": "premium-prize-bond-rs-40000",
}
# Draw dates per denomination counted by hand from the survey (see docs/research/nss-source-survey.md).
DRAWS = {"rs-100": 31, "rs-200": 31, "rs-750": 32, "rs-1500": 31, "premium-25000": 23, "premium-40000": 30}


def page_links(slug: str) -> list[DiscoveredLink]:
    html = (HTML / f"{PAGES[slug]}.html").read_text(encoding="utf-8")
    return parse_denomination_page(html, f"{BASE}{PAGES[slug]}/", slug)


def test_index_lists_the_six_known_pages_and_no_unknown_ones():
    entries = parse_index((HTML / "index.html").read_text(encoding="utf-8"), BASE, KNOWN)
    assert sorted(e.slug for e in entries if e.slug) == sorted(KNOWN.values())
    assert all(e.slug for e in entries)
    assert {e.url for e in entries} >= {"https://savings.gov.pk/rs-200-prize-bond-draw"}


def test_unknown_denomination_page_is_reported_not_created():
    html = '<a href="/rs-7500-prize-bond-draw">Rs. 7500 Prize Bond Draw List</a><a href="/about">About</a>'
    entries = parse_index(html, BASE, KNOWN)
    assert [(e.slug, e.url) for e in entries] == [(None, "https://savings.gov.pk/rs-7500-prize-bond-draw")]


@pytest.mark.parametrize("slug", list(DRAWS))
def test_every_page_yields_the_expected_number_of_draw_dates(slug):
    links = page_links(slug)
    assert all(link.denomination_slug == slug for link in links)
    assert len(select_sources(links)) == DRAWS[slug]


def test_total_links_match_the_survey():
    assert sum(len(page_links(slug)) for slug in DRAWS) == 186


def test_date_comes_from_the_link_text_even_when_the_file_name_disagrees():
    link = next(link for link in page_links("rs-200") if link.link_text == "16-06-2022")
    assert link.parsed_date == datetime.date(2022, 6, 16)
    assert link.url.endswith("15-06-2022-Rs-200.txt")  # the file name says the 15th
    assert link.date_source == "text"


def test_link_text_with_a_format_suffix_still_gives_the_date():
    links = [lk for lk in page_links("rs-100") if lk.parsed_date == datetime.date(2025, 8, 15)]
    assert sorted(lk.ext for lk in links) == ["pdf", "txt"]
    assert {lk.link_text for lk in links} == {"15-08-2025 (text)", "15-08-2025 (pdf)"}


def test_date_less_link_text_falls_back_to_the_file_name_and_says_so():
    link = next(lk for lk in page_links("rs-100") if lk.link_text == "100_170826_Txt")
    assert link.parsed_date == datetime.date(2026, 8, 17)
    assert link.date_source == "filename"
    assert any("file name" in note for note in link.notes)


def test_link_without_any_usable_date_is_kept_but_has_no_date():
    html = '<h2>2026</h2><h2><a href="/wp-content/uploads/2026/01/result.txt">latest results</a></h2>'
    [link] = parse_denomination_page(html, BASE, "rs-200")
    assert link.parsed_date is None and link.date_source == "none"
    assert select_sources([link]) == {}


def test_year_heading_mismatch_is_noted():
    html = '<h2>2025</h2><h2><a href="/wp-content/uploads/2026/01/x.txt">15-01-2026</a></h2>'
    [link] = parse_denomination_page(html, BASE, "rs-200")
    assert any("differs from the page heading" in n for n in link.notes)


def test_impossible_dates_are_not_accepted():
    html = '<h2><a href="/wp-content/uploads/2026/01/x_310226.txt">31-02-2026</a></h2>'
    [link] = parse_denomination_page(html, BASE, "rs-200")
    assert link.parsed_date is None


def test_select_sources_prefers_text_over_pdf_and_scans():
    links = {lk.ext: lk for lk in page_links("rs-1500") if lk.parsed_date == datetime.date(2026, 2, 16)}
    assert set(links) == {"txt", "pdf"}
    chosen = select_sources(list(links.values()))
    assert chosen[datetime.date(2026, 2, 16)].ext == "txt"


def test_pdf_only_draws_are_still_selected():
    chosen = select_sources(page_links("rs-1500"))
    assert chosen[datetime.date(2026, 8, 17)].ext == "pdf"


def test_non_upload_links_are_ignored():
    html = '<h2>2026</h2><a href="https://savings.gov.pk/contact">15-01-2026</a>'
    assert parse_denomination_page(html, BASE, "rs-200") == []

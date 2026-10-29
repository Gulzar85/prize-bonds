import datetime
import json
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apps.draws.ingestion.extractors import extract
from apps.draws.ingestion.parser import parse

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "draws"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))["fixtures"]
HAND_READ = [entry for entry in MANIFEST if entry["verification"] == "hand-read"]


def parsed(relative_name: str):
    path = FIXTURES / relative_name
    return parse(extract(path.read_bytes(), path.suffix).text)


# --- golden tests: expected values come from the hand-read manifest, not from the parser ------------------------------


@pytest.mark.parametrize("entry", HAND_READ, ids=[e["file"].rsplit("/", 1)[-1] for e in HAND_READ])
def test_golden_hand_read_fixtures(entry):
    expected = entry["expected"]
    result = parsed(entry["file"].removeprefix("tests/fixtures/draws/"))

    assert result.draw_number == expected["draw_number"]
    expected_date = expected["draw_date"]
    assert result.draw_date == (datetime.date.fromisoformat(expected_date) if expected_date else None)
    if expected["city"] is None:
        assert result.city is None
    else:
        assert result.city.lower() == expected["city"].lower().removeprefix("sbp bsc ")

    for want in expected["tiers"]:
        tier = result.tier(want["rank"])
        assert tier is not None, f"tier {want['rank']} missing"
        assert tier.amount_pkr == want["amount_pkr"]
        assert tier.announced_count == want["announced_count"]
        if "numbers" in want:
            assert list(tier.numbers) == want["numbers"]
        if "first" in want:
            assert tier.numbers[0] == want["first"]
            assert tier.numbers[-1] == want["last"]
        if "grid_first_in_reading_order" in want:
            assert tier.numbers[0] == want["grid_first_in_reading_order"]
            assert tier.numbers[-1] == want["grid_last_real_in_reading_order"]
        if "filler_cells" in want:
            assert tier.filler_count == want["filler_cells"]


def test_the_hand_read_set_covers_every_denomination():
    assert {e["denomination_page"] for e in HAND_READ} == {e["denomination_page"] for e in MANIFEST}


# --- behaviour on real files -------------------------------------------------------------------------------------------


GAP = "layout-gap-found-by-live-dry-run"
SURVEY_TXT = [e for e in MANIFEST if e["file"].endswith(".txt") and GAP not in e["selected_because"]]
LAYOUT_GAP_TXT = [e for e in MANIFEST if GAP in e["selected_because"]]


def _parse_entry(entry):
    path = FIXTURES / entry["file"].removeprefix("tests/fixtures/draws/")
    return parse(extract(path.read_bytes(), "txt").text)


def test_every_surveyed_txt_fixture_parses_without_unrecognised_lines_and_with_three_tiers():
    assert len(SURVEY_TXT) == 39
    for entry in SURVEY_TXT:
        result = _parse_entry(entry)
        assert [t.rank for t in result.tiers] == [1, 2, 3], entry["file"]
        assert not [w for w in result.warnings if w.code == "unrecognised_lines"], entry["file"]
        assert result.tier(3).numbers, entry["file"]


def test_layouts_found_by_the_live_dry_run_are_now_understood():
    """Files the first full dry run could not read: each now yields three tiers with first/second amounts."""
    assert len(LAYOUT_GAP_TXT) == 8
    for entry in LAYOUT_GAP_TXT:
        result = _parse_entry(entry)
        assert [t.rank for t in result.tiers] == [1, 2, 3], entry["file"]
        assert result.tier(1).amount_pkr and result.tier(2).amount_pkr, entry["file"]


def test_amount_without_rs_and_third_tier_heading_variants():
    result = parse("20th Draw\nFirst prize Rs. 5/-\n011964\nThird Prize of 300,000/- each\n000277 | 071106\n")
    assert result.tier(3).amount_pkr == 300000
    bare = parse("52nd Draw\nFirst Prize of Rs. 700,000/-\n171732\nPrizes of Rs. 1,000/- each\n000177 | 042172\n")
    assert (bare.tier(3).amount_pkr, bare.tier(3).numbers) == (1000, ("000177", "042172"))


def test_numbers_before_the_word_price_and_amounts_without_rs():
    text = "100TH DRAW\n871778 First price 1,500,000\n249962 Second price 500,000\n448780 Second price 500,000\n"
    result = parse(text)
    assert result.tier(1).numbers == ("871778",) and result.tier(1).amount_pkr == 1_500_000
    assert result.tier(2).numbers == ("249962", "448780") and result.tier(2).amount_pkr == 500_000


def test_count_line_in_the_header_and_a_third_tier_without_heading():
    rows = "\n".join("\t".join(f"{r * 6 + c + 1:06d}" for c in range(6)) for r in range(3))
    text = (
        "100TH DRAW OF RS.750/- HELD AT FAISALABAD ON 15TH OCTOBER, 2024 - 1696 PRIZES OF RS.9,300/- EACH\n"
        "871778 First price 1,500,000\n249962 Second price 500,000\n" + rows + "\n"
    )
    result = parse(text)
    assert result.tier(3).amount_pkr == 9300 and result.tier(3).announced_count == 1696
    assert len(result.tier(3).numbers) == 18 and result.tier(2).numbers == ("249962",)
    assert "third_tier_without_heading" in {w.code for w in result.warnings}
    assert result.draw_date == datetime.date(2024, 10, 15)


def test_digits_typed_with_spaces_are_joined_and_flagged():
    result = parse("15th DRAW\nFirst Prize of Rs. 80,000,000/-\n9 9 8 0 2 9\nSecond Prize of Rs. 1/-\n213322 457930\n")
    assert result.tier(1).numbers == ("998029",)
    assert "spaced_digits_joined" in {w.code for w in result.warnings}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("held on 10th Dec, 2020 at X", datetime.date(2020, 12, 10)),
        ("held today the 15th December, 2023 (Friday)", datetime.date(2023, 12, 15)),
        ("held on 15th Sept 2024", datetime.date(2024, 9, 15)),
        ("held on 1 Jan. 2025", datetime.date(2025, 1, 1)),
        ("HELD ON 31-12-2025", datetime.date(2025, 12, 31)),
    ],
)
def test_date_formats(text, expected):
    assert parse(f"5th DRAW OF Rs.200/- {text}\nFirst Prize of Rs.5\n111111\n").draw_date == expected


def test_denomination_with_and_without_the_rupee_slash():
    spelled = parse("Draw Result of Rs.25,000 Denomination Premium 20th Draw\nFirst Prize of Rs.5\n111111\n")
    assert spelled.denomination_value == 25000
    assert parse("DRAW OF Rs.40000/- Premium\nFirst Prize of Rs.5\n111111\n").denomination_value == 40000


def test_four_digit_number_is_kept_as_printed_not_padded():
    result = parsed("rs-750-prize-bond-draw/750_15102026-1.txt")
    assert result.tier(2).numbers == ("7447", "827353", "876615")


def test_announced_total_of_the_107th_draw_is_exposed_as_the_third_count():
    result = parsed("rs-200-prize-bond-draw/200_150926.txt")
    tier3 = result.tier(3)
    assert tier3.announced_count == 2400  # the source's number; its meaning is judged by the validator
    assert len(tier3.numbers) == 2394
    assert tier3.filler_count == 6
    assert result.grid_cells == 2400


def test_official_part_i_pdf_summary_gives_authoritative_counts():
    result = parsed("rs-200-prize-bond-draw/15-12-2023.pdf")
    assert result.draw_date == datetime.date(
        2023, 12, 15
    )  # "held today the 15th December, 2023", not the 14-10 cut-off
    assert [t.announced_count for t in result.tiers] == [1, 5, 2394]
    assert result.announced_total == 2400


def test_docx_first_page_has_no_third_tier():
    result = parsed("rs-100-prize-bond-draw/35th-draw-of-100-Student-Welfare-Bonds.docx")
    assert result.tier(3) is None
    assert result.tier(2).numbers == ("212399", "288254", "660539")


def test_typos_in_tier_headings_are_understood():
    text = (
        "40000 DRAW\nFirst Prize of Rs.1,000\n111111\nSecond Prize of Rs.500\n222222\nThird Price of Rs.100\n333333\n"
    )
    assert [t.numbers for t in parse(text).tiers] == [("111111",), ("222222",), ("333333",)]
    assert parse("First Pprize of Rs.5\n111111\n").tier(1).numbers == ("111111",)


def test_filler_variants_are_dropped_and_counted():
    result = parse("Third Prize of Rs.10\n111111\t222222\txxxxxx\n333333\t*****\tXXXXX\n")
    assert result.tier(3).numbers == ("111111", "222222", "333333")
    assert result.tier(3).filler_count == 3
    assert result.grid_cells == 6


def test_unknown_lines_are_reported_not_dropped_silently():
    result = parse("First Prize of Rs.5\n111111\nsomething odd 42 here\n")
    codes = {w.code: w for w in result.warnings}
    assert codes["unrecognised_lines"].context["total"] == 1
    assert "something odd" in codes["unrecognised_lines"].context["lines"][0]["text"]


def test_missing_header_fields_are_warnings_not_errors():
    result = parse("First Prize of Rs.5\n111111\n")
    codes = {w.code for w in result.warnings}
    assert {"header_no_draw_number", "header_no_date", "header_no_city", "header_no_denomination"} <= codes
    assert result.draw_number is None and result.draw_date is None


def test_impossible_header_date_is_flagged():
    result = parse("5th DRAW OF Rs.200/- HELD ON 31-02-2026 AT SBP BSC Multan\nFirst Prize of Rs.5\n111111\n")
    assert result.draw_date is None
    assert "header_invalid_date" in {w.code for w in result.warnings}


def test_header_with_several_dates_and_no_held_is_flagged():
    result = parse("5th DRAW OF Rs.200/-\n01-01-2026 and 02-01-2026\nFirst Prize of Rs.5\n111111\n")
    assert result.draw_date == datetime.date(2026, 1, 1)
    assert "header_multiple_dates" in {w.code for w in result.warnings}


def test_header_dict_is_json_friendly():
    result = parsed("rs-200-prize-bond-draw/200_150926.txt")
    header = result.header_dict()
    assert header["draw_date"] == "2026-09-15"
    assert json.dumps(header)


# --- property tests: a synthetic file generator must be recovered exactly ------------------------------------------


def _numbers(min_size: int, max_size: int):
    return st.lists(st.integers(0, 999_999).map("{:06d}".format), min_size=min_size, max_size=max_size, unique=True)


@st.composite
def synthetic_draw(draw):
    pool = draw(_numbers(30, 220))
    n1, n2 = draw(st.integers(1, 2)), draw(st.integers(1, 5))
    first, second, third = pool[:n1], pool[n1 : n1 + n2], pool[n1 + n2 :]
    columns = draw(st.integers(3, 13))
    separator = draw(st.sampled_from(["\t", " | ", "   ", "\t\t", " \t "]))
    newline = draw(st.sampled_from(["\n", "\r\n", "\r"]))
    filler = draw(st.sampled_from(["XXXXXX", "xxxxxx", "XXXXX", "******"]))
    page_every = draw(st.sampled_from([0, 5, 17, 50]))
    layout = draw(st.sampled_from(["new", "old"]))
    draw_number = draw(st.integers(1, 200))
    day, month, year = draw(st.integers(1, 28)), draw(st.integers(1, 12)), draw(st.integers(2019, 2030))
    city = draw(st.sampled_from(["Multan", "Karachi", "Rawalpindi", "Muzaffarabad", "Quetta"]))
    value = draw(st.sampled_from([100, 200, 750, 1500, 25000, 40000]))
    amounts = (
        draw(st.integers(100_000, 90_000_000)),
        draw(st.integers(10_000, 50_000_000)),
        draw(st.integers(100, 500_000)),
    )
    leading_space = draw(st.sampled_from(["", " ", "\t\t\t", "      "]))

    rows = [third[i : i + columns] for i in range(0, len(third), columns)]
    pad = (-len(third)) % columns
    if pad and rows:
        rows[-1] = rows[-1] + [filler] * pad
    grid: list[str] = []
    for index, row in enumerate(rows, start=1):
        if page_every and index % page_every == 1:
            grid.append(f"{leading_space}Page {index // page_every + 1}/9")
        grid.append(separator.join(row) + draw(st.sampled_from(["", " ", "\t"])))

    date_text = f"{day:02d}-{month:02d}-{year}"
    if layout == "new":
        lines = [
            f"{leading_space}{draw_number}th DRAW OF Rs.{value:,}/- DENOMINATION PREMIUM PRIZE BONDS",
            f"HELD ON {date_text}  AT SBP BSC {city}",
            "",
            f"1st Prize:{separator}Rs. {amounts[0]:,}/-",
            f"{n1:02d} Prize{'s' if n1 > 1 else ''}:{separator}" + separator.join(first),
            f"2nd Prize{separator}Rs. {amounts[1]:,}/- Each",
            f"{n2:02d} Prizes{separator}" + separator.join(second),
            f"({len(third)} Prizes of Rs.{amounts[2]}/- Each)",
        ]
    else:
        lines = [
            f"DRAW OF Rs.{value}/- PRIZE BOND",
            f"HELD AT {city.upper()}",
            f"Draw No.{draw_number}TH",
            f"Series:\tCommon Draw\tDate:{day:02d}/{month:02d}/{year}",
            "-------------------------------------",
            f"First Prize of Rs.{amounts[0]:,} /-",
            separator.join(first),
            "-------------------------------------",
            f"Second Prize of Rs.Rs.{amounts[1]:,}/- each.",
            " | ".join(second),
            "-------------------------------------",
            f"{len(third)} Prize(s) of {amounts[2]}/- Each",
        ]
    text = newline.join(lines + grid) + newline
    return text, dict(
        first=first,
        second=second,
        third=third,
        fillers=pad if rows else 0,
        draw_number=draw_number,
        date=datetime.date(year, month, day),
        city=city,
        value=value,
        amounts=amounts,
    )


@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
@given(synthetic_draw())
def test_parser_recovers_exactly_what_the_generator_wrote(case):
    text, want = case
    result = parse(extract(text.encode(), "txt").text)
    assert [list(t.numbers) for t in result.tiers] == [want["first"], want["second"], want["third"]]
    assert [t.amount_pkr for t in result.tiers] == list(want["amounts"])
    assert result.tier(3).announced_count == len(want["third"])
    assert result.tier(3).filler_count == want["fillers"]
    assert result.draw_number == want["draw_number"]
    assert result.draw_date == want["date"]
    assert result.city.lower() == want["city"].lower()
    assert result.denomination_value == want["value"]
    assert not [w for w in result.warnings if w.code == "unrecognised_lines"]

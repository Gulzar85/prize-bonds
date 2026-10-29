import datetime
from pathlib import Path

import pytest

from apps.draws.ingestion.extractors import extract
from apps.draws.ingestion.parser import parse
from apps.draws.ingestion.types import ParsedTier, ParseResult, Severity
from apps.draws.ingestion.validators import ValidationContext, has_errors, summarise, validate

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "draws"
DATE = datetime.date(2026, 9, 15)


def result(**overrides) -> ParseResult:
    """A clean synthetic result; overrides replace whole fields."""
    third = tuple(f"{n:06d}" for n in range(100, 110))
    fields = {
        "header_text": "x",
        "draw_number": 107,
        "draw_date": DATE,
        "city": "Multan",
        "denomination_value": 200,
        "tiers": (
            ParsedTier(1, 750_000, 1, ("000001",)),
            ParsedTier(2, 250_000, 2, ("000002", "000003")),
            ParsedTier(3, 1_250, 10, third),
        ),
        "grid_cells": 10,
        "grid_rows": (third[:5], third[5:]),
    }
    fields.update(overrides)
    return ParseResult(**fields)


def ctx(**overrides) -> ValidationContext:
    return ValidationContext(**{"link_date": DATE, "expected_denomination_value": 200, **overrides})


def codes(findings, severity=None):
    return {f.code for f in findings if severity is None or f.severity is severity}


def with_tiers(*tiers):
    return result(tiers=tuple(tiers))


def test_a_clean_result_has_no_findings():
    assert validate(result(), ctx()) == []


# --- errors --------------------------------------------------------------------------------------------------------


def test_header_date_mismatch_is_an_error_and_a_match_is_not():
    findings = validate(result(), ctx(link_date=datetime.date(2026, 9, 16)))
    assert codes(findings, Severity.ERROR) == {"header_date_mismatch"}
    assert validate(result(draw_date=None), ctx()) == []  # unknown header date: the warning lives in the parser


def test_denomination_mismatch():
    assert codes(validate(result(denomination_value=750), ctx()), Severity.ERROR) == {"denomination_mismatch"}
    assert validate(result(denomination_value=None), ctx()) == []


@pytest.mark.parametrize("missing_rank", [1, 2, 3])
def test_missing_or_empty_tier_is_an_error(missing_rank):
    r = result()
    kept = tuple(t for t in r.tiers if t.rank != missing_rank)
    assert "tier_missing" in codes(validate(result(tiers=kept), ctx()), Severity.ERROR)
    emptied = tuple(ParsedTier(t.rank, t.amount_pkr, None, ()) if t.rank == missing_rank else t for t in r.tiers)
    assert "tier_missing" in codes(validate(result(tiers=emptied), ctx()), Severity.ERROR)


def test_wrong_digit_length_is_an_error_never_padded():
    tiers = (ParsedTier(1, 1, 1, ("000001",)), ParsedTier(2, 1, 1, ("7447",)), ParsedTier(3, 1, None, ("000009",)))
    findings = validate(result(tiers=tiers), ctx())
    error = next(f for f in findings if f.code == "wrong_digit_length")
    assert error.severity is Severity.ERROR
    assert error.context["numbers"] == [{"rank": 2, "number": "7447"}]


def test_number_in_two_tiers_and_duplicate_within_a_tier():
    two = (ParsedTier(1, 1, 1, ("000001",)), ParsedTier(2, 1, 1, ("000001",)), ParsedTier(3, 1, None, ("000009",)))
    assert "number_in_two_tiers" in codes(validate(result(tiers=two), ctx()), Severity.ERROR)
    dup = (
        ParsedTier(1, 1, 1, ("000001",)),
        ParsedTier(2, 1, 1, ("000002",)),
        ParsedTier(3, 1, None, ("000009", "000009")),
    )
    assert "duplicate_number" in codes(validate(result(tiers=dup), ctx()), Severity.ERROR)


def test_announced_count_mismatch_is_an_error():
    tiers = (
        ParsedTier(1, 1, 1, ("000001",)),
        ParsedTier(2, 1, 5, ("000002",)),
        ParsedTier(3, 1, 3, ("000009", "000010")),
    )
    errors = [f for f in validate(result(tiers=tiers), ctx()) if f.code == "announced_count_mismatch"]
    assert [f.context["rank"] for f in errors] == [2, 3]


def test_announced_total_mismatch_is_an_error():
    assert "announced_total_mismatch" in codes(validate(result(announced_total=99), ctx()), Severity.ERROR)
    assert validate(result(announced_total=13), ctx()) == []  # 1 + 2 + 10


@pytest.mark.parametrize("amount", [None, 0])
def test_amount_not_positive_is_an_error(amount):
    tiers = (
        ParsedTier(1, amount, 1, ("000001",)),
        ParsedTier(2, 1, 1, ("000002",)),
        ParsedTier(3, 1, None, ("000009",)),
    )
    assert "amount_not_positive" in codes(validate(result(tiers=tiers), ctx()), Severity.ERROR)


# --- warnings ------------------------------------------------------------------------------------------------------


def test_announced_count_that_equals_the_total_is_a_warning_not_an_error():
    r = result()
    tiers = (*r.tiers[:2], ParsedTier(3, 1_250, 13, r.tiers[2].numbers))  # 1 + 2 + 10
    findings = validate(result(tiers=tiers), ctx())
    assert codes(findings) == {"announced_count_is_total"}
    assert not has_errors(findings)


def test_missing_third_count_is_a_warning():
    r = result()
    tiers = (*r.tiers[:2], ParsedTier(3, 1_250, None, r.tiers[2].numbers))
    assert codes(validate(result(tiers=tiers), ctx())) == {"announced_count_missing"}


def test_draw_number_not_sequential():
    assert codes(validate(result(), ctx(previous_draw_number=105))) == {"draw_number_not_sequential"}
    assert validate(result(), ctx(previous_draw_number=106)) == []
    assert validate(result(draw_number=None), ctx(previous_draw_number=106)) == []


def test_grid_not_sorted_names_the_column():
    rows = (("000100", "000200"), ("000050", "000300"))
    findings = validate(result(grid_rows=rows), ctx())
    assert codes(findings) == {"grid_not_sorted"}
    assert findings[0].context["columns"] == [1]
    ok = (("000100", "000200"), ("000150", "XXXXXX"))
    assert validate(result(grid_rows=ok), ctx()) == []


def test_amount_changed_against_previous_draw():
    findings = validate(result(), ctx(previous_amounts={1: 750_000, 2: 250_000, 3: 1_000}))
    assert codes(findings) == {"amount_changed"}
    assert findings[0].context["rank"] == 3


def test_third_count_differs_from_previous():
    assert codes(validate(result(), ctx(previous_third_count=1199))) == {"third_count_differs_from_previous"}
    assert validate(result(), ctx(previous_third_count=10)) == []


def test_large_revision_diff():
    assert codes(validate(result(), ctx(diff_ratio=0.02))) == {"revision_diff_large"}
    assert validate(result(), ctx(diff_ratio=0.01)) == []


def test_summarise_counts_codes():
    findings = validate(result(announced_total=99, draw_date=DATE), ctx(link_date=datetime.date(2026, 1, 1)))
    assert summarise(findings)["header_date_mismatch"] == 1


# --- real files ---------------------------------------------------------------------------------------------------


def validate_fixture(name: str, **context):
    path = FIXTURES / name
    return validate(parse(extract(path.read_bytes(), path.suffix).text), ValidationContext(**context))


def test_draw_107_has_only_the_total_count_warning():
    findings = validate_fixture(
        "rs-200-prize-bond-draw/200_150926.txt",
        link_date=datetime.date(2026, 9, 15),
        expected_denomination_value=200,
    )
    assert codes(findings) == {"announced_count_is_total"}


def test_draw_108_four_digit_second_prize_blocks_publication():
    findings = validate_fixture(
        "rs-750-prize-bond-draw/750_15102026-1.txt",
        link_date=datetime.date(2026, 10, 15),
        expected_denomination_value=750,
    )
    assert has_errors(findings)
    assert codes(findings, Severity.ERROR) == {"wrong_digit_length"}


def test_wrong_page_denomination_is_caught_on_a_real_file():
    findings = validate_fixture("rs-200-prize-bond-draw/200_150926.txt", expected_denomination_value=750)
    assert "denomination_mismatch" in codes(findings, Severity.ERROR)


def test_first_page_only_docx_is_missing_its_third_tier():
    findings = validate_fixture(
        "rs-100-prize-bond-draw/35th-draw-of-100-Student-Welfare-Bonds.docx", expected_denomination_value=100
    )
    assert "tier_missing" in codes(findings, Severity.ERROR)


def test_rs100_may_2026_typo_in_third_prize_amount_is_flagged_against_history():
    findings = validate_fixture(
        "rs-100-prize-bond-draw/Rs-100-Prize-Bond-Draw-May-2026.txt",
        expected_denomination_value=100,
        previous_amounts={1: 700_000, 2: 200_000, 3: 1_000},
    )
    assert any(f.code == "amount_changed" and f.context["amount"] == 100 for f in findings)

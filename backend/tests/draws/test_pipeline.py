import datetime

import pytest

from apps.draws import alerts
from apps.draws.ingestion.discovery import DiscoveredLink
from apps.draws.ingestion.fetcher import FetchFailed, NotModified
from apps.draws.ingestion.storage import raw_key, read_raw, store_raw
from apps.draws.models import Draw, DrawRevision, PrizeTier, WinningNumber
from apps.draws.services import pipeline
from apps.draws.services.diff import compute_diff
from tests.draws.conftest import SEPT_15, FakeFetcher, fetched, fixture_bytes, make_operator, rs200

pytestmark = pytest.mark.django_db

DRAW_107 = fixture_bytes("rs-200-prize-bond-draw/200_150926.txt")
DRAW_108_750 = fixture_bytes("rs-750-prize-bond-draw/750_15102026-1.txt")


def link(
    date=SEPT_15, url="https://savings.gov.pk/wp-content/uploads/2026/09/200_150926.txt", ext="txt", text="15-09-2026"
):
    return DiscoveredLink("rs-200", text, date, "text", url, ext, "2026")


# --- create_revision --------------------------------------------------------------------------------------------------


def test_a_clean_file_becomes_a_reviewable_revision_with_tiers_and_numbers(sent_alerts):
    draw, _ = pipeline.get_or_create_draw(rs200(), SEPT_15)
    revision = pipeline.create_revision(draw, DRAW_107, "txt", source_url="https://savings.gov.pk/x.txt")

    revision.refresh_from_db()
    assert revision.status == DrawRevision.Status.NEEDS_REVIEW
    assert revision.extraction_method == "TXT"
    assert revision.revision_no == 1
    assert revision.parse_errors == []
    assert [w["code"] for w in revision.parse_warnings] == ["announced_count_is_total"]
    assert revision.parsed_header["draw_number"] == 107
    assert [t.rank for t in revision.tiers.all()] == [1, 2, 3]
    third = revision.tiers.get(rank=3)
    assert (third.amount_pkr, third.announced_count, third.parsed_count) == (1250, 2400, 2394)
    assert WinningNumber.objects.filter(revision=revision).count() == 1 + 5 + 2394
    assert WinningNumber.objects.filter(revision=revision, number="516806", tier__rank=1).exists()

    draw.refresh_from_db()
    assert (draw.status, draw.draw_number, draw.city) == (Draw.Status.IN_REVIEW, 107, "Muzaffarabad")
    assert read_raw(revision.storage_key) == DRAW_107  # the raw file is kept byte for byte
    assert revision.storage_key == raw_key("rs-200", SEPT_15, revision.sha256, "txt")
    assert sent_alerts == []


def test_a_file_with_errors_still_reaches_review_with_the_findings(sent_alerts):
    draw, _ = pipeline.get_or_create_draw(rs200().__class__.objects.get(slug="rs-750"), datetime.date(2026, 10, 15))
    revision = pipeline.create_revision(draw, DRAW_108_750, "txt")
    assert revision.status == DrawRevision.Status.NEEDS_REVIEW
    assert [e["code"] for e in revision.parse_errors] == ["wrong_digit_length"]
    assert revision.parse_errors[0]["context"]["numbers"] == [{"rank": 2, "number": "7447"}]


def test_unreadable_file_fails_the_revision_and_alerts(sent_alerts):
    draw, _ = pipeline.get_or_create_draw(rs200(), SEPT_15)
    revision = pipeline.create_revision(draw, b"%PDF-1.4 garbage", "pdf")
    assert revision.status == DrawRevision.Status.PARSE_FAILED
    assert revision.parse_errors[0]["code"] == "extraction_failed"
    assert not revision.tiers.exists()
    draw.refresh_from_db()
    assert draw.status == Draw.Status.FAILED
    assert [a[0] for a in sent_alerts] == [alerts.PARSE_FAILURE]


def test_header_facts_never_overwrite_the_draw_and_conflicts_are_errors(sent_alerts):
    draw, _ = pipeline.get_or_create_draw(rs200(), SEPT_15)
    draw.draw_number = 99
    draw.city = "Karachi"
    draw.save()
    revision = pipeline.create_revision(draw, DRAW_107, "txt")
    assert "draw_number_mismatch" in {e["code"] for e in revision.parse_errors}
    draw.refresh_from_db()
    assert (draw.draw_number, draw.city) == (99, "Karachi")

    owner, _ = pipeline.get_or_create_draw(rs200(), datetime.date(2026, 9, 14))
    pipeline.create_revision(owner, DRAW_107, "txt")  # takes draw number 107
    other, _ = pipeline.get_or_create_draw(rs200(), datetime.date(2026, 9, 16))
    clash = pipeline.create_revision(other, DRAW_107, "txt")
    assert "draw_number_conflict" in {e["code"] for e in clash.parse_errors}
    other.refresh_from_db()
    assert other.draw_number is None  # uniqueness is protected


def test_duplicate_numbers_are_reported_not_stored_twice(sent_alerts):
    text = b"7th DRAW OF Rs.200/-\nFirst Prize of Rs.5\n111111\nSecond Prize of Rs.4\n222222\nThird Prize of Rs.3\n111111\t333333\n"
    draw, _ = pipeline.get_or_create_draw(rs200(), SEPT_15)
    revision = pipeline.create_revision(draw, text, "txt")
    assert "number_in_two_tiers" in {e["code"] for e in revision.parse_errors}
    assert WinningNumber.objects.filter(revision=revision, number="111111").count() == 1


def test_only_pending_revisions_can_be_processed(sent_alerts):
    draw, _ = pipeline.get_or_create_draw(rs200(), SEPT_15)
    revision = pipeline.create_revision(draw, DRAW_107, "txt")
    with pytest.raises(ValueError, match="PENDING"):
        pipeline.process_revision(revision, DRAW_107)


def test_scanned_pdf_without_tesseract_fails_clearly(sent_alerts):
    draw, _ = pipeline.get_or_create_draw(rs200(), SEPT_15)
    pdf = fixture_bytes("rs-100-prize-bond-draw/Rs-100-53-Draw-16-02-2026-Karachi.pdf")
    revision = pipeline.create_revision(draw, pdf, "pdf")
    # Whether Tesseract is installed or not, a scan must never silently publish: it fails or goes to review.
    assert revision.status in {DrawRevision.Status.PARSE_FAILED, DrawRevision.Status.NEEDS_REVIEW}
    if revision.status == DrawRevision.Status.NEEDS_REVIEW:
        assert revision.extraction_method == "OCR"


def test_ocr_results_are_always_flagged(sent_alerts, monkeypatch):
    from apps.draws.ingestion.extractors import ocr as ocr_module

    monkeypatch.setattr(ocr_module.pytesseract, "get_tesseract_version", lambda: "5")
    monkeypatch.setattr(ocr_module.pytesseract, "image_to_string", lambda image, **kw: "")
    text = DRAW_107.decode().replace("\r\n", "\n")
    monkeypatch.setattr(ocr_module.pytesseract, "image_to_string", lambda image, **kw: text)
    draw, _ = pipeline.get_or_create_draw(rs200(), SEPT_15)
    pdf = fixture_bytes("rs-100-prize-bond-draw/Rs-100-53-Draw-16-02-2026-Karachi.pdf")
    revision = pipeline.create_revision(draw, pdf, "pdf")
    assert revision.extraction_method == "OCR"
    assert revision.status == DrawRevision.Status.NEEDS_REVIEW
    assert "extraction_warning" in {w["code"] for w in revision.parse_warnings}


# --- ingest_link (crawling) -----------------------------------------------------------------------------------------


def test_ingest_link_creates_a_revision_for_a_new_file(sent_alerts):
    fetcher = FakeFetcher(fetched(DRAW_107))
    result = pipeline.ingest_link(fetcher, link(), rs200())
    assert result.outcome == pipeline.NEW_REVISION
    assert result.revision.etag == '"e1"'
    assert result.revision.draw.draw_date == SEPT_15
    assert fetcher.calls[0]["etag"] == ""  # nothing known yet


def test_unchanged_file_is_a_no_op_via_conditional_get(sent_alerts):
    fetcher = FakeFetcher(fetched(DRAW_107), NotModified("u"))
    first = pipeline.ingest_link(fetcher, link(), rs200())
    again = pipeline.ingest_link(fetcher, link(), rs200())
    assert again.outcome == pipeline.UNCHANGED
    assert fetcher.calls[1]["etag"] == '"e1"'  # validators were sent
    assert DrawRevision.objects.count() == 1
    assert again.revision == first.revision


def test_same_content_with_a_new_etag_is_still_a_no_op(sent_alerts):
    fetcher = FakeFetcher(fetched(DRAW_107), fetched(DRAW_107, etag='"e2"'))
    pipeline.ingest_link(fetcher, link(), rs200())
    again = pipeline.ingest_link(fetcher, link(), rs200())
    assert again.outcome == pipeline.UNCHANGED
    assert DrawRevision.objects.count() == 1


def test_changed_content_creates_revision_two_with_a_diff(sent_alerts):
    changed = DRAW_107.replace(b"516806", b"516807")
    fetcher = FakeFetcher(fetched(DRAW_107), fetched(changed, etag='"e2"'))
    pipeline.ingest_link(fetcher, link(), rs200())
    result = pipeline.ingest_link(fetcher, link(), rs200())
    assert result.outcome == pipeline.NEW_REVISION
    revision = result.revision
    assert revision.revision_no == 2
    assert revision.diff_from_previous["tiers"]["1"]["added"] == ["516807"]
    assert revision.diff_from_previous["tiers"]["1"]["removed"] == ["516806"]
    assert revision.diff_from_previous["changed_numbers"] == 2


def test_changed_url_for_a_known_draw_is_a_new_revision(sent_alerts):
    revised = DRAW_107.replace(b"516806", b"516807")
    fetcher = FakeFetcher(
        fetched(DRAW_107), fetched(revised, url="https://savings.gov.pk/wp-content/uploads/2026/12/Revised.txt")
    )
    pipeline.ingest_link(fetcher, link(), rs200())
    result = pipeline.ingest_link(
        fetcher, link(url="https://savings.gov.pk/wp-content/uploads/2026/12/Revised.txt"), rs200()
    )
    assert result.outcome == pipeline.NEW_REVISION
    assert fetcher.calls[1]["etag"] == ""  # validators belong to the old URL, so they are not sent


def test_revision_on_a_published_draw_alerts(sent_alerts, operator):
    from apps.draws.services import review

    fetcher = FakeFetcher(fetched(DRAW_107), fetched(DRAW_107.replace(b"516806", b"516807"), etag='"e2"'))
    first = pipeline.ingest_link(fetcher, link(), rs200()).revision
    review.approve_revision(first.pk, operator, "checked")
    pipeline.ingest_link(fetcher, link(), rs200())
    assert alerts.REVISION_DETECTED in [a[0] for a in sent_alerts]
    first.draw.refresh_from_db()
    assert first.draw.status == Draw.Status.PUBLISHED  # still serving the approved revision


def test_fetch_failure_alerts_and_stores_nothing(sent_alerts):
    result = pipeline.ingest_link(FakeFetcher(FetchFailed("boom")), link(), rs200())
    assert result.outcome == pipeline.FAILED
    assert [a[0] for a in sent_alerts] == [alerts.FETCH_FAILURE]
    assert DrawRevision.objects.count() == 0


def test_unrecognised_layout_alerts(sent_alerts):
    weird = DRAW_107 + b"\r\nsomething completely unexpected 42\r\n"
    pipeline.ingest_link(FakeFetcher(fetched(weird)), link(), rs200())
    assert alerts.UNKNOWN_LAYOUT in [a[0] for a in sent_alerts]


# --- manual upload --------------------------------------------------------------------------------------------------


def test_manual_upload_runs_the_same_pipeline_and_records_the_uploader(sent_alerts, operator):
    revision = pipeline.upload_revision(rs200(), SEPT_15, DRAW_107, "result.txt", operator, max_bytes=10**6)
    assert revision.uploaded_by == operator
    assert revision.status == DrawRevision.Status.NEEDS_REVIEW
    assert revision.link_text == "manual upload: result.txt"
    assert PrizeTier.objects.filter(revision=revision).count() == 3


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [("x.exe", b"abc", "Unsupported"), ("x.txt", b"", "empty"), ("noext", b"abc", "Unsupported")],
)
def test_manual_upload_rejects_bad_files(sent_alerts, operator, filename, content, message):
    with pytest.raises(pipeline.UploadRejected, match=message):
        pipeline.upload_revision(rs200(), SEPT_15, content, filename, operator, max_bytes=10**6)


def test_manual_upload_rejects_oversize_and_repeats_and_non_operators(sent_alerts, operator):
    with pytest.raises(pipeline.UploadRejected):
        pipeline.upload_revision(rs200(), SEPT_15, DRAW_107, "x.txt", operator, max_bytes=100)
    pipeline.upload_revision(rs200(), SEPT_15, DRAW_107, "x.txt", operator, max_bytes=10**6)
    with pytest.raises(pipeline.UploadRejected, match="already"):
        pipeline.upload_revision(rs200(), SEPT_15, DRAW_107, "x.txt", operator, max_bytes=10**6)
    no_mfa = make_operator(mfa=False)
    with pytest.raises(pipeline.UploadRejected, match="MFA"):
        pipeline.upload_revision(rs200(), SEPT_15, DRAW_107.replace(b"516806", b"1"), "y.txt", no_mfa, max_bytes=10**6)


# --- storage and diff ------------------------------------------------------------------------------------------------


def test_store_raw_is_idempotent_and_content_addressed():
    key = raw_key("rs-200", SEPT_15, "ab" * 32, ".TXT")
    assert key == f"raw/rs-200/2026-09-15/{'ab' * 32}.txt"
    assert store_raw(key, b"one") == key
    assert store_raw(key, b"one") == key
    assert read_raw(key) == b"one"


def test_diff_reports_numbers_header_and_amount_changes():
    diff = compute_diff(
        {1: {"1"}, 3: {"3", "4"}},
        {1: {"1"}, 3: {"4", "5"}},
        {"city": "Multan", "draw_number": 5},
        {"city": "Karachi", "draw_number": 5},
        {3: 1000},
        {3: 100},
    )
    assert diff["tiers"]["3"]["added"] == ["5"] and diff["tiers"]["3"]["removed"] == ["3"]
    assert diff["header"] == {"city": ["Multan", "Karachi"]}
    assert diff["amounts"] == {"3": [1000, 100]}
    assert diff["changed_numbers"] == 2
    assert diff["ratio"] == pytest.approx(2 / 4)
    assert not diff["is_empty"]
    assert compute_diff({1: {"1"}}, {1: {"1"}}, {}, {})["is_empty"]
    assert compute_diff({}, {}, {}, {})["ratio"] == 0.0


def test_revision_parse_fields_cannot_change_after_processing(sent_alerts):
    draw, _ = pipeline.get_or_create_draw(rs200(), SEPT_15)
    revision = pipeline.create_revision(draw, DRAW_107, "txt")
    revision.sha256 = "0" * 64
    with pytest.raises(ValueError, match="immutable"):
        revision.save(update_fields=["sha256"])

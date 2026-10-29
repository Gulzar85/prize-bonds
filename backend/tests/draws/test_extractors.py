import subprocess
from pathlib import Path

import pytesseract
import pytest

from apps.draws.ingestion.extractors import (
    ExtractionError,
    ExtractorUnavailable,
    NoTextLayer,
    extract,
)
from apps.draws.ingestion.extractors import doc as doc_module
from apps.draws.ingestion.extractors import ocr as ocr_module
from apps.draws.ingestion.extractors.docx import extract_docx
from apps.draws.ingestion.extractors.pdf import extract_pdf_text
from apps.draws.ingestion.extractors.txt import extract_txt

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "draws"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# --- txt -----------------------------------------------------------------------------------------------------------


def test_txt_normalises_line_endings_and_keeps_content():
    result = extract_txt(fixture("rs-200-prize-bond-draw/200_150926.txt"))
    assert result.method == "TXT"
    assert "\r" not in result.text
    assert "107th DRAW OF Rs.200/-" in result.text
    assert "516806" in result.text
    assert result.warnings == ()


def test_txt_falls_back_to_cp1252_with_a_warning():
    result = extract_txt(b"Rs. 18, 500 \x96 prize")
    assert "–" in result.text
    assert result.warnings == ("Decoded as cp1252 (not valid UTF-8)",)


def test_txt_strips_bom_and_nuls():
    assert extract_txt(b"\xef\xbb\xbf" + b"A" * 2000 + b"\x00\r\n").text == "A" * 2000 + "\n"


@pytest.mark.parametrize("data", [b"", b"   \n\t "], ids=["empty", "blank"])
def test_txt_rejects_empty(data):
    with pytest.raises(ExtractionError, match="empty"):
        extract_txt(data)


def test_txt_rejects_binary():
    with pytest.raises(ExtractionError, match="binary"):
        extract_txt(b"\x00\x01\x02" * 100 + b"text")


# --- pdf -----------------------------------------------------------------------------------------------------------


def test_pdf_with_text_layer():
    result = extract_pdf_text(fixture("rs-200-prize-bond-draw/15-12-2023.pdf"))
    assert result.method == "PDF_TEXT"
    assert "96th DRAW" in result.text


@pytest.mark.parametrize(
    "name",
    [
        "rs-100-prize-bond-draw/Rs-100-53-Draw-16-02-2026-Karachi.pdf",  # image only
        "rs-100-prize-bond-draw/Draw-Result.pdf",  # scanner watermark only
    ],
)
def test_scanned_pdf_has_no_text_layer(name):
    with pytest.raises(NoTextLayer):
        extract_pdf_text(fixture(name))


def test_pdf_page_limit_is_enforced():
    with pytest.raises(ExtractionError, match="limit is 1"):
        extract_pdf_text(fixture("rs-200-prize-bond-draw/15-12-2023.pdf"), max_pages=1)


def test_pdf_garbage_is_rejected():
    with pytest.raises(ExtractionError):
        extract_pdf_text(b"%PDF-1.4 this is not a pdf")


# --- docx ----------------------------------------------------------------------------------------------------------


def test_docx_reads_paragraphs_and_tables():
    result = extract_docx(fixture("rs-100-prize-bond-draw/35th-draw-of-100-Student-Welfare-Bonds.docx"))
    assert result.method == "DOCX"
    assert "35th DRAW" in result.text
    assert "1203" in result.text
    assert "\t" in result.text  # table rows are tab separated


def test_docx_garbage_is_rejected():
    with pytest.raises(ExtractionError, match="Unreadable"):
        extract_docx(b"not a zip")


# --- doc (LibreOffice) ---------------------------------------------------------------------------------------------


def test_doc_requires_libreoffice(monkeypatch):
    monkeypatch.setattr(doc_module, "find_soffice", lambda: None)
    with pytest.raises(ExtractorUnavailable):
        doc_module.extract_doc(b"data")


def test_doc_converts_with_a_controlled_subprocess(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        workdir = Path(kwargs["cwd"])
        (workdir / "input.txt").write_text("97th DRAW OF Rs.750/-\n", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(doc_module, "find_soffice", lambda: "/usr/bin/soffice")
    monkeypatch.setattr(doc_module.subprocess, "run", fake_run)
    result = doc_module.extract_doc(b"binary doc", timeout=5)
    assert result.method == "DOC_CONVERT"
    assert "97th DRAW" in result.text
    argv, kwargs = calls[0]
    assert argv[0] == "/usr/bin/soffice"
    assert "--headless" in argv
    assert kwargs["timeout"] == 5
    assert kwargs["check"] is True
    assert "shell" not in kwargs
    assert set(kwargs["env"]) <= {"PATH", "HOME", "SYSTEMROOT"}


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (subprocess.TimeoutExpired("soffice", 1), "timed out"),
        (subprocess.CalledProcessError(2, "soffice"), "exit code 2"),
    ],
)
def test_doc_subprocess_failures(monkeypatch, error, message):
    def fake_run(*args, **kwargs):
        raise error

    monkeypatch.setattr(doc_module, "find_soffice", lambda: "/usr/bin/soffice")
    monkeypatch.setattr(doc_module.subprocess, "run", fake_run)
    with pytest.raises(ExtractionError, match=message):
        doc_module.extract_doc(b"x")


def test_doc_without_output(monkeypatch):
    monkeypatch.setattr(doc_module, "find_soffice", lambda: "/usr/bin/soffice")
    monkeypatch.setattr(doc_module.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0))
    with pytest.raises(ExtractionError, match="no output"):
        doc_module.extract_doc(b"x")


# --- ocr -----------------------------------------------------------------------------------------------------------


def test_ocr_requires_tesseract(monkeypatch):
    def missing():
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(ocr_module.pytesseract, "get_tesseract_version", missing)
    with pytest.raises(ExtractorUnavailable):
        ocr_module.extract_ocr(b"x")


def test_ocr_result_is_always_flagged(monkeypatch):
    monkeypatch.setattr(ocr_module.pytesseract, "get_tesseract_version", lambda: "5.3")
    monkeypatch.setattr(ocr_module.pytesseract, "image_to_string", lambda image, **kw: "001462 074018\n")
    data = fixture("rs-100-prize-bond-draw/Rs-100-53-Draw-16-02-2026-Karachi.pdf")
    result = ocr_module.extract_ocr(data)
    assert result.method == "OCR"
    assert result.text.count("001462") == 3  # one per page
    assert "verified" in result.warnings[0]


def test_ocr_page_limit_and_empty_output(monkeypatch):
    monkeypatch.setattr(ocr_module.pytesseract, "get_tesseract_version", lambda: "5.3")
    data = fixture("rs-100-prize-bond-draw/Rs-100-53-Draw-16-02-2026-Karachi.pdf")
    with pytest.raises(ExtractionError, match="limit is 1"):
        ocr_module.extract_ocr(data, max_pages=1)
    monkeypatch.setattr(ocr_module.pytesseract, "image_to_string", lambda image, **kw: "  ")
    with pytest.raises(ExtractionError, match="no text"):
        ocr_module.extract_ocr(data)


# --- dispatch ------------------------------------------------------------------------------------------------------


def test_dispatch_by_extension():
    assert extract(fixture("rs-200-prize-bond-draw/200_150926.txt"), "TXT").method == "TXT"
    assert extract(fixture("rs-200-prize-bond-draw/15-12-2023.pdf"), ".pdf").method == "PDF_TEXT"
    docx = fixture("rs-100-prize-bond-draw/35th-draw-of-100-Student-Welfare-Bonds.docx")
    assert extract(docx, "docx").method == "DOCX"


def test_dispatch_scanned_pdf_falls_back_to_ocr(monkeypatch):
    monkeypatch.setattr(ocr_module.pytesseract, "get_tesseract_version", lambda: "5.3")
    monkeypatch.setattr(ocr_module.pytesseract, "image_to_string", lambda image, **kw: "123456")
    result = extract(fixture("rs-100-prize-bond-draw/Rs-100-53-Draw-16-02-2026-Karachi.pdf"), "pdf")
    assert result.method == "OCR"


def test_dispatch_rejects_unknown_extension():
    with pytest.raises(ExtractionError, match="Unsupported"):
        extract(b"x", "xlsx")


def test_every_fixture_with_a_text_source_extracts():
    """Smoke test over all committed TXT fixtures: nothing raises and every file yields non-empty text."""
    files = sorted(FIXTURES.glob("*/*.txt"))
    assert len(files) == 47
    for path in files:
        assert extract(path.read_bytes(), "txt").text.strip(), path.name

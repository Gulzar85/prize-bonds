from apps.draws.ingestion.extractors.base import ExtractedText, ExtractionError, NoTextLayer
from apps.draws.ingestion.extractors.doc import extract_doc
from apps.draws.ingestion.extractors.docx import extract_docx
from apps.draws.ingestion.extractors.ocr import extract_ocr
from apps.draws.ingestion.extractors.pdf import extract_pdf_text
from apps.draws.ingestion.extractors.txt import extract_txt

SUPPORTED_EXTENSIONS = frozenset({"txt", "pdf", "doc", "docx"})


def extract(data: bytes, ext: str) -> ExtractedText:
    """Pick the extractor for a file extension. Scanned PDFs fall back to OCR (flagged by a warning)."""
    ext = ext.lower().lstrip(".")
    if ext == "txt":
        return extract_txt(data)
    if ext == "pdf":
        try:
            return extract_pdf_text(data)
        except NoTextLayer:
            return extract_ocr(data)
    if ext == "docx":
        return extract_docx(data)
    if ext == "doc":
        return extract_doc(data)
    raise ExtractionError(f"Unsupported file type: .{ext}")

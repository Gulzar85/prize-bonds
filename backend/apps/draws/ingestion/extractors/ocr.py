import io

import pdfplumber
import pytesseract
from pdfminer.pdfparser import PDFSyntaxError
from pdfplumber.utils.exceptions import PdfminerException

from apps.draws.ingestion.extractors.base import MAX_PDF_PAGES, ExtractedText, ExtractionError, ExtractorUnavailable

OCR_DPI = 300
# Single uniform block of text, digits and the filler letter only: the draw lists contain nothing else of value.
_TESSERACT_CONFIG = "--psm 6 -c tessedit_char_whitelist=0123456789Xx|:./-()"
_OCR_WARNING = "Text read by OCR; every number must be verified against the source before approval"


def extract_ocr(data: bytes, max_pages: int = MAX_PDF_PAGES, timeout: int = 120) -> ExtractedText:
    """OCR a scanned PDF. The result is always routed to human review by the pipeline."""
    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError as exc:
        raise ExtractorUnavailable("Tesseract is not installed") from exc
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > max_pages:
                raise ExtractionError(f"PDF has {len(pdf.pages)} pages, limit is {max_pages}")
            parts = [
                pytesseract.image_to_string(
                    page.to_image(resolution=OCR_DPI).original, config=_TESSERACT_CONFIG, timeout=timeout
                )
                for page in pdf.pages
            ]
    except (PDFSyntaxError, PdfminerException, ValueError, RuntimeError) as exc:
        raise ExtractionError(f"OCR failed: {exc}") from exc
    text = "\n".join(parts)
    if not text.strip():
        raise ExtractionError("OCR produced no text")
    return ExtractedText(text=text, method="OCR", warnings=(_OCR_WARNING,))

import io

import pdfplumber
from pdfminer.pdfparser import PDFSyntaxError
from pdfplumber.utils.exceptions import PdfminerException

from apps.draws.ingestion.extractors.base import MAX_PDF_PAGES, ExtractedText, ExtractionError, NoTextLayer

#: A page with fewer characters than this is treated as having no text layer (scanner watermarks such as
#: "CamScanner" are about 10 characters).
MIN_CHARS_PER_PAGE = 50


def extract_pdf_text(data: bytes, max_pages: int = MAX_PDF_PAGES) -> ExtractedText:
    """Extract the text layer of a PDF; raise :class:`NoTextLayer` for scanned documents."""
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > max_pages:
                raise ExtractionError(f"PDF has {len(pdf.pages)} pages, limit is {max_pages}")
            pages = [page.extract_text() or "" for page in pdf.pages]
    except (PDFSyntaxError, PdfminerException, ValueError) as exc:
        raise ExtractionError(f"Unreadable PDF: {exc}") from exc
    if not pages:
        raise ExtractionError("PDF has no pages")
    if sum(len(p.strip()) for p in pages) < MIN_CHARS_PER_PAGE * len(pages):
        raise NoTextLayer("PDF has no usable text layer")
    return ExtractedText(text="\n".join(pages), method="PDF_TEXT")

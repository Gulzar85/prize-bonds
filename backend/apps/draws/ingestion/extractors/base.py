from dataclasses import dataclass

#: Hard ceiling for any document extractor (pages of a PDF).
MAX_PDF_PAGES = 30
#: Wall-clock limit for external converters (LibreOffice) in seconds.
SUBPROCESS_TIMEOUT = 90


class ExtractionError(Exception):
    """The file could not be turned into text (corrupt, too large, unsupported)."""


class NoTextLayer(ExtractionError):
    """A PDF has pages but no text layer (a scan); only OCR can read it."""


class ExtractorUnavailable(ExtractionError):
    """A required external tool (LibreOffice, Tesseract) is not installed."""


@dataclass(frozen=True)
class ExtractedText:
    text: str
    method: str  # one of DrawRevision.Extraction values
    warnings: tuple[str, ...] = ()

import io
import zipfile

import docx
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from apps.draws.ingestion.extractors.base import ExtractedText, ExtractionError


def _iter_blocks(document: DocxDocument):  # type: ignore[no-untyped-def]
    """Paragraphs and tables in document order."""
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def extract_docx(data: bytes) -> ExtractedText:
    """Extract paragraphs and table cells (tab-separated rows) in document order."""
    try:
        document = docx.Document(io.BytesIO(data))
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise ExtractionError(f"Unreadable DOCX: {exc}") from exc
    lines: list[str] = []
    for block in _iter_blocks(document):
        if isinstance(block, Paragraph):
            lines.append(block.text)
        else:
            for row in block.rows:
                lines.append("\t".join(cell.text.strip() for cell in row.cells))
    text = "\n".join(lines)
    if not text.strip():
        raise ExtractionError("DOCX contains no text")
    return ExtractedText(text=text, method="DOCX")

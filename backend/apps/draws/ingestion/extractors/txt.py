from apps.draws.ingestion.extractors.base import ExtractedText, ExtractionError

#: A real text file never contains NUL bytes; binary content masquerading as .txt is rejected.
_MAX_NUL_RATIO = 0.001


def extract_txt(data: bytes) -> ExtractedText:
    """Decode a text file: UTF-8 first, then cp1252; normalise line endings; drop a BOM."""
    if not data.strip():
        raise ExtractionError("File is empty")
    if data.count(b"\x00") / len(data) > _MAX_NUL_RATIO:
        raise ExtractionError("File looks binary, not text")
    warnings: list[str] = []
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
        warnings.append("Decoded as cp1252 (not valid UTF-8)")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return ExtractedText(text=text, method="TXT", warnings=tuple(warnings))

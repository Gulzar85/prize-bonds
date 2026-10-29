# ADR-0007: Parser architecture

## Status
Accepted (Phase 1)

## Context
The files are hand-prepared and inconsistent: seven layouts so far, typos ("Third Price", "Pprize"), glued words in PDF text,
filler cells written `XXXXXX`, `XXXXX`, `xxxxxx` or `******`, CR-only line endings, headers that move after the tier headings,
no date or city in most 2026 files, and a 4-digit prize number in one file.

## Decision
- **Three pure stages with no Django imports**: *extractors* (bytes to text), the *parser* (text to `ParseResult`, a frozen
  dataclass) and *validators* (`ParseResult` plus context to findings). They are fast to test and reusable.
- **The parser is section-driven and tolerant.** Tier headings (`1st|first ... prize`, "N Prizes of Rs.X") switch the current
  tier; numeric-only lines are numbers or grid rows; lines without a digit are ignored; known boilerplate (signatures, page
  markers) is noise. Dates accept numeric and spelled-out forms, preferring the one after "held". Official "Part-I" summary
  lines ("N Prizes of Rs.X each, M Prizes in each series") supply authoritative per-tier counts.
- **No silent fallbacks.** Anything the parser cannot place is reported as an `unrecognised_lines` warning with the line;
  missing header fields are warnings. Numbers are kept exactly as printed and never padded, so a wrong length is a validator
  ERROR rather than a guess.
- **Validators return structured findings** (`code`, `severity`, `message`, `context`). ERROR blocks publication until a
  reviewer overrides it with a written note; WARNING does not. Context-dependent checks (link date, denomination, previous
  draw's amounts and third-prize count) are passed in, so the functions stay pure.
- **Extraction**: UTF-8 then cp1252 for text; `pdfplumber` for PDFs with a page limit and a "no text layer" signal; `python-docx`
  including tables; LibreOffice headless for `.doc` in a temp directory with a scrubbed environment and a hard timeout;
  Tesseract OCR only for scanned PDFs, always warned and always reviewed. All extraction runs on the `ingestion` Celery queue.
- **Testing**: golden tests compare against values read by a person (`manifest.json`, `verification: hand-read`), never against
  the parser's own output; a Hypothesis generator writes synthetic files with varied separators, line endings, page markers,
  fillers and layouts and the parser must recover exactly what was written; one test per finding code at both severities.

## Consequences
- New layouts surface as warnings in review instead of wrong data; adding a layout means adding a regex and a fixture.
- Only 6 of 55 fixtures are hand-read so far; the others must be read before golden tests may assert on them.
- Third-prize grids are column-major (ascending down each column), so reading order is not sorted order; the sort check is
  per column.

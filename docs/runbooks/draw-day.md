# Draw-day runbook

Where to look: **Django admin > Draws > Draw revisions** (the review queue), *Ingestion runs*, *Draw schedules*,
*Outbox events*. You need to be in the `data_operator` group with MFA enabled.

## 1. The draw does not appear
Polling starts at 12:00 on the scheduled date (every 30 minutes until 23:30, then hourly for three days). If nothing shows up:
1. Open the denomination page on savings.gov.pk. If the file is not listed yet, wait; NSS often publishes in the evening.
2. Check *Ingestion runs*: a FAILED or PARTIAL run with an error summary means the crawl could not fetch (site down, TLS,
   robots.txt).
3. If the file is listed but nothing arrived, run it by hand:
   `python manage.py backfill_draws --denomination rs-200 --since 2026`.
4. After three days the **draw_not_found** alert fires once. Upload the file manually (section 3) if the website is broken.

## 2. A parse failed
A **parse_failure** alert and a revision in `PARSE_FAILED` mean the file could not be read (corrupt, unsupported, a scan
without Tesseract installed, or a `.doc` without LibreOffice). Do not guess numbers. Either fix the environment and re-crawl,
or obtain a readable copy and upload it (section 3). Reject the failed revision with a note explaining why.

An **unknown_layout** alert means the parser met lines it does not understand; the review screen lists them. Compare against
the source before approving.

## 3. Manual upload
Admin > Draw revisions > *Upload a result manually*. Choose the denomination, the draw date and the file (TXT, PDF, DOC, DOCX,
at most 20 MB). It runs the same pipeline and lands in the queue. **A different operator must approve it** (four-eyes).
Use this for draws that exist only as scans or "first page" files: the file must contain all three prize tiers.

## 4. Approving a revision
Open the revision from the queue and check, in this order:
1. **Header** matches the draw (number, date, city, denomination).
2. **Announced vs parsed counts** match. "Announced equals the total of all tiers" is a known harmless warning.
3. **Findings**. Errors block approval; read each one. To publish despite an error (for example a number printed with the
   wrong length in the source) tick the override box and say what you checked.
4. **Source excerpts and the 20 sampled numbers** against the source file.
5. For a revision of a published draw, read the **diff**: added and removed numbers per tier, and header changes.

Write a note and press *approve*. The draw is published and a `draw.published` (or `draw.revised`) outbox event is created.
OCR results and any revision touching a published draw deserve a second look at the source file.

## 5. Rolling back a bad publication
Never delete. Obtain the correct file, upload it (section 3) and approve it: the bad revision becomes SUPERSEDED, the draw
serves the corrected numbers and a `draw.revised` event with the diff is emitted so downstream notifications can be corrected.

## Backfill
`python manage.py backfill_draws [--denomination SLUG] [--since YEAR] [--dry-run] [--approve-clean --as EMAIL]`.
Always run a `--dry-run` first: it downloads, parses and validates but writes nothing and prints the findings summary.

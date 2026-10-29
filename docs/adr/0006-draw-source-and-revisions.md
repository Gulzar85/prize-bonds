# ADR-0006: Draw source and revisions

## Status
Accepted (Phase 1)

## Context
Results are published by National Savings on savings.gov.pk as one WordPress page per denomination, each linking to
result files (mostly `.txt`, some `.pdf`, `.doc`, `.docx`). The survey (`docs/research/nss-source-survey.md`) found 178 draws
across six denominations, inconsistent file names, upload folders that do not match the draw month, several files for one
draw, files replaced in place after publication, scanned PDFs, and a server that sends an incomplete TLS chain and gzips
its `.txt` files. A wrong published number tells a family they won (or did not), so correctness beats speed.

## Decision
- **The draw date comes from the link text** (`DD-MM-YYYY` prefix, tolerating suffixes like ` (pdf)`), never from the file
  name or upload folder. If the link has no date the file name is used and a note is kept; if neither works the link is
  skipped and alerted. The date in the file is then *compared* with the link date; a mismatch is an ERROR.
- **One preferred file per draw date**: `txt > docx > doc > pdf`. A scanned PDF is used only when nothing else exists.
- **Every distinct file is a `DrawRevision`.** A changed URL or a changed SHA-256 for a known draw creates revision *n+1*;
  an unchanged file (HTTP 304, or identical hash) is a no-op. Revisions are immutable (source and parse fields cannot be
  changed after parsing, enforced in `DrawRevision.save`), are never deleted, and keep the raw file in private storage
  under a content-addressed key. The draw serves its `published_revision` until a newer one is approved.
- **Fetching is polite and safe**: descriptive User-Agent with a contact address, `robots.txt`, one request per 2 s, backoff
  on 429/5xx, 20 MB cap while streaming, content type checked against the extension, host allow-list re-checked on every
  redirect, `https` only.
- **TLS**: the site omits its real intermediate ("GoGetSSL RSA DV SSL CA 2"), so OpenSSL cannot build the chain (Windows
  can, via AIA). We pin that public intermediate in `apps/draws/ingestion/certs/` and verify against *certifi plus the pinned
  intermediate*. Verification is never disabled. If the site changes its CA, fetches fail loudly (a FETCH_FAILURE alert)
  rather than silently trusting anything.
- **Compressed bodies are decoded exactly once** (a bug found by the first live run: the site gzips `.txt`).
- **Announced counts**: the figure printed in the header is usually the third-prize count (excluding filler cells), but in
  at least one file (Rs 200 draw 107) and in the official Part-I summaries it is the total of all tiers. The validator accepts
  either, flags the second as a WARNING, and errors on anything else.

## Consequences
- Re-crawling is cheap and idempotent; a weekly full crawl detects in-place replacements.
- Draws published only as scans need OCR (always routed to human review) or a manual upload.
- Some draws exist only as a "first page" (`.docx`/`.doc` named *First-Page*) with no third-prize grid; they fail the
  `tier_missing` validation and must be completed by a manual upload.
- Pinning an intermediate is operational debt: it expires in 2035 and must be revisited if NSS changes certificate authority.

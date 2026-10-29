# NSS draw source survey

Surveyed **2026-10-29** from `savings.gov.pk`. 10 page requests (robots, index, sitemap, 6 denomination pages, lookup) plus 55 file downloads, at least 2 s apart, with the
User-Agent `PrizeBondTrackerSurvey/0.1 (+mailto:gulzar85@hotmail.com)`. `robots.txt` allows everything except `/wp-admin/`.

Scratch outputs (catalog, downloads, analysis scripts) are not committed; the fixtures and `manifest.json` are in
`backend/tests/fixtures/draws/`.

## 1. Pages

| Denomination | Page | Draw dates listed | First | Latest |
|---|---|---|---|---|
| Rs 100 (Student Welfare) | `/rs-100-prize-bond-draw/` | 31 | 2019-02-15 | 2026-08-17 |
| Rs 200 | `/rs-200-prize-bond-draw/` | 31 | 2019-03-15 | 2026-09-15 |
| Rs 750 | `/rs-750-prize-bond-draw/` | 32 | 2019-01-15 | 2026-10-15 |
| Rs 1,500 | `/rs-1500-prize-bond-draw/` | 31 | 2019-02-15 | 2026-08-17 |
| Premium Rs 25,000 | `/premium-prize-bond-rs-25000/` | 23 | 2021-03-10 | 2026-09-10 |
| Premium Rs 40,000 | `/premium-prize-bond-rs-40000/` | 30 | 2019-03-11 | 2026-09-10 |

Total **178 draws, 186 file links**. The index lists exactly these six (no unknown denominations today). Links are
`<h2>` year headings followed by one `<h2>` per link; the link sits inside the date heading. Page URLs on the
index have no trailing slash and redirect to the slash form.

**Cadence:** Rs 100 and Rs 1,500 quarterly-ish (Feb/May/Aug/Nov), Rs 200 and Rs 750 quarterly, premium bonds
quarterly (Mar/Jun/Sep/Dec, on the 10th). Rs 750 has 2026-10-15 already, so "latest" moves.

## 2. Links by extension

| Denomination | txt | pdf | doc / docx |
|---|---|---|---|
| Rs 100 | 28 | 4 | 1 docx |
| Rs 200 | 30 | 1 | 0 |
| Rs 750 | 31 | 1 | 1 doc |
| Rs 1,500 | 30 | 4 | 0 |
| Premium 25,000 | 22 | 2 | 0 |
| Premium 40,000 | 29 | 2 | 0 |
| **Total** | **170** | **14** | **2** |

Links per year are 4 per denomination per year except where noted (Rs 100/1,500 2025 have 5/6 from duplicates).

## 3. Anomalies

1. **Draws with no TXT, only a non-text file (9):** Premium 25,000 2023-12-11 (PDF), Premium 40,000 2023-12-12
   (PDF), Rs 100 2019-08-15 (PDF), Rs 100 2020-08-15 (PDF), Rs 100 2021-08-15 (docx), Rs 200 2023-12-15 (PDF),
   Rs 750 2024-01-15 (doc), Rs 1,500 **2026-08-17 (PDF, the most recent Rs 1,500 draw)**.
2. **14 of 16 PDFs have no text layer** (scans, several made with CamScanner). Only
   `15-12-2023.pdf` (Rs 200) and the Rs 25,000 2026-03-10 PDF have real text. So **OCR is required, not optional**,
   for 6 draws, including a live one.
3. **Several files for one draw (8 draws):** link text carries a format suffix, e.g. `15-08-2025 (text)` and
   `15-08-2025 (pdf)`, or two identical `10-03-2026` links (premium pages: one PDF, one TXT).
4. **Link text that is not a date:** `100_170826_Txt` (Rs 100, 2026-08-17); the date exists only in the file name
   (`170826`). Other suffix cases: `16-02-2026  (Txt File)`, `15-05-2025 (PDF File)`, `15-01-2026 (Text)`.
5. **File name date disagrees with link date (13):** e.g. `15-11-2014-Rs-100.txt` linked as 15-11-2024;
   `15-06-2022-Rs-200.txt` linked as 16-06-2022; `Rs-40000-10-12-2025.txt`; `17-08-2020-Rs-1500.txt` linked 15-08-2020.
   File names are unreliable in both directions.
6. **Upload folder is not the draw month for 131 of 186 files.** 130 were bulk re-uploaded to `/2024/11/`.
7. **Revisions:** `Revised-Draw-Result-of-Rs.-200-Denominatio.txt` (draw 2025-06-16, uploaded `/2025/12/`) and
   `1500-101-Updated-Draw-List.txt` (2025-02-17). The link URL changed in place, so detection is by URL or hash change
   under the same heading, not by a new link.
8. **No broken links** found in the 55 downloaded; every request returned 200 with the expected content type
   (`text/plain`, `application/pdf`, `application/msword`, `…wordprocessingml.document`). The server dropped one
   keep-alive connection mid-run: the fetcher needs retries and should not reuse connections blindly.
9. **No `ETag`/`Last-Modified` check was possible** beyond recording them in the manifest; see `etag` and
   `last_modified` per entry for what the server sends.
10. **TLS:** Python/OpenSSL **fails certificate verification** (`unable to get local issuer certificate`) while
    Windows' store accepts it, i.e. the server sends an incomplete chain and relies on AIA fetching. A Linux
    container will fail the same way. Decision needed in Phase 1 (see plan): bundle the missing intermediate
    certificate and pin it, never disable verification.

## 4. Layout variants (txt)

Whitespace is tab and space mixed; line endings CRLF; all 39 TXT fixtures decode as ASCII/UTF-8 (cp1252 fallback
not exercised). Excerpts are redacted to first lines.

| Id | Seen in | Header | Tier sections | Grid |
|---|---|---|---|---|
| L-NEW-12COL-PAGED | Rs 200 draw 107 | `107th DRAW OF Rs.200/- DENOMINATION PREMIUM PRIZE BONDS` / `HELD ON 15-09-2026  AT SBP BSC Muzaffarabad` | `1st Prize:  Rs. 750,000/-` / `01 Prize:   516806`, `2nd Prize Rs. 250,000/- Each` / `05 Prizes  n n n n n`, `(2400 Prizes of Rs.1250/- Each)` | 12 columns, `Page n/4`, `XXXXXX` fillers |
| L-750-PART2 | Rs 750 draw 108 | `108th DRAW OF RS.750/- DENOMINATION NATIONAL PRIZE BONDS` / `HELD ON 15-10-2026 AT SBP BSC RAWALPINDI` | `First Prize of Rs.1,500,000/-`, `Second Prize … each (03 Prizes)`, `(1696 Prizes of Rs. 9,300/- each)`, `PART -II  Page No.1/3` | 11 columns, `XXXXXX` |
| L-100-STUDENT-WELFARE | Rs 100 draw 55 | `Draw Result of Rs. 100/- Denomination Student Welfare Prize Bonds – 55th Draw` (no date, no city) | `First Prize of Rs. 700,000/-`, `Second Prize of Rs. 200,000/- each` (count not stated), `(1199 Prizes of Rs.1,000/- each)  Page No.1` | 12 columns, **lowercase** `xxxxxx` |
| L-PREMIUM-13COL | Premium 25,000 / 40,000 | `23rd DRAW OF Rs.25,000/- … PREMIUM PRIZE BONDS (REGISTERED)` / `HELD ON 10-09-2026 AT SBP BSC QUETTA` | `1st Prize: Rs. … Each` / `02 Prizes n n` (**more than one first-prize number possible**), `2nd Prize …`, `(700 Prizes of Rs.300,000/- Each)` | 13 columns, lowercase or upper `x` fillers |
| L-1500-SECTIONED | Rs 1,500 draw 106 | `DRAW RESULT OF RS.1500/- DENOMINATION NATIONAL PRIZE BONDS - 106TH DRAW` (no date, no city) | `First Prize of Rs. 3,000,000/-`, `Second Prize … (each)`, `Third Prize of Rs. 18, 500/-` (note the space), **no count line** | 6 columns, `XXXXX` (5 X) |
| L-105TH-LOWER | Rs 200 draw 105 | `105th draw of Prize Bond, Rs.200/- denomination at SBP (BSC) Faisalabad on 16.03.2026(Monday)` (dots as date separators) | `1st Prize of Rs. 750,000`, `2nd Prize … 5 numbers on one line`, `Third Prize of Rs. 1250` | 6 columns, many fillers |
| L-OLD-SERIES | Rs 200 2019–2022, Rs 750/Rs 1,500 2019–2020 | `DRAW OF Rs.200/- PRIZE BOND`, `HELD AT RAWALPINDI`, `Draw No.84TH`, `Series: Common Draw  Date:15/12/2020` (slashes) | `First Prize of Rs.750,000 /-`, `Second Prize of Rs.Rs.250,000/- each.` (doubled `Rs.`), `2394 Prize(s) of 1250/- Each` | multi-column, no `Page` markers |

More variants exist in the 16 files not yet read in detail (e.g. `Draw No.:` + city on one line in 2019 files).
All header dates seen: `dd-mm-yyyy`, `dd.mm.yyyy`, `dd/mm/yyyy`.

## 5. Digit lengths

All **third-prize numbers are 6 digits** (zero padded) in every TXT fixture. **One first/second-tier number is 4
digits**: Rs 750 draw 108, second prize `7447`. It may be a typo or a lost leading zero (`007447`); the parser must
flag it, never pad or guess. No 7-digit numbers seen in TXT. Denomination `number_length` = 6 for all six today.

## 6. Announced-count rule (verdict)

Evidence from every TXT that states a count (exploratory counts, 39 files; the parser is not written yet):

- For Rs 100 (1,199), Rs 750/1,500 (1,696), Premium 25,000 (700), Premium 40,000 (660) and **Rs 200 up to 2022
  (`2394 Prize(s) of 1250/- Each`)** the announced number equals the **third-tier count**; fillers (`XXXXXX`) are
  extra and are not counted.
- Rs 200 draw 107 states `(2400 Prizes …)` while the grid holds **2,394 real numbers + 6 fillers**, and
  2,394 is the third-tier count of every earlier Rs 200 draw. So 2400 = 1 + 5 + 2,394, i.e. **the total of all tiers**.
  The hypothesis in the brief is confirmed for that file.
- Many files (Rs 1,500 draw 106, Rs 200 draw 105, most 2026 files) carry **no count line at all**.
- The `.docx` (Rs 100, draw 35) says `The following 1203 common numbers were drawn`: also a **total** (1 + 3 + 1,199).

Proposed rule: `announced` is accepted if it equals `third_count` (normal) or `first+second+third_count` (flag
`announced_count_is_total`, WARNING). Neither match = ERROR; absent = WARNING. Because the meaning varies per file,
never infer it from the draw number alone.

**Suspicious counts (need a human or a second source):** Rs 100 draw 54 (1,144 vs usual 1,199), Rs 750 draw 105
(1,660 vs 1,696), Premium 40,000 draw 36 (572 vs 660), Premium 25,000 2026-06-10 (600 vs 700), Premium 40,000
2019-03-11 (1,144 vs stated 660). These could be truncated uploads or real changes; the file alone cannot tell.

## 7. Layout facts that differ from the brief

- First tier can hold **more than one number** (Premium 25,000 draw 23: `02 Prizes`).
- Filler token length and case vary: `XXXXXX`, `XXXXX`, `xxxxxx`.
- Most 2026 files have **no city or date in the header**; the date comes from the link (or from the file name when
  the link has no date).
- Rs 100 is "Student Welfare" bonds; "National" for others; "Premium (Registered)" for 25,000/40,000. The Rs 200
  header says "PREMIUM PRIZE BONDS" in one file and "NATIONAL PRIZE BONDS" in another. Header wording must not drive the
  `kind`.
- Grid order is **column-major** and ascending down each column (checked on Rs 200 draw 107: 12 columns x 200 rows;
  fillers occupy the tail of the last column), so reading order is not sorted order.

## 8. Official lookup (`/latest/results.php`)

One request. `POST` form: `country` (denomination select, includes legacy 7500, 15000), `state` (draw date, filled by
JavaScript), range `range_from`/`range_to`, and a comma-separated number list. The page states *"We are updating the
Database for Draw Results. If you do not find draw dates, do not worry"* and *"Errors and omissions are Expected"*.
Verdict: **not reliable enough to use as an automatic verifier** and it needs a JS-populated date list. Suitable only
as an optional manual spot-check link for reviewers; no scraper will be built.

## 9. Fixture set

`backend/tests/fixtures/draws/` holds **55 files (21 MB)**: latest 3 dates per denomination, oldest per denomination,
all 16 non-TXT files, both revisions, all date-mismatch and multi-file cases. `manifest.json` has source URL, SHA-256,
size, content type, `ETag`, `Last-Modified`, link text and selection reasons per file.

**Hand verification status:** expected values (draw number, date, city, tier amounts, announced counts, first/last
numbers) were read by eye for **6 of 55** files, one per denomination (`verification: hand-read`). The other 49 are
marked `pending-hand-read` and must be read before golden tests may assert on them.

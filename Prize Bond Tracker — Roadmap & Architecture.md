# Prize Bond Tracker — Roadmap & Architecture

Oct 24, 2026 · @Gulzar Ahmed

## Product scope

A public, multi-tenant app where any Pakistani household tracks its National Savings prize bonds and is alerted automatically when one wins. Launch on web, Android and desktop (Electron) from one Django 6.1 API.

**What changes because it is public**

- **Tenancy:** every signup gets its own Household workspace. All data is scoped to a household; nothing is shared across tenants.
- **Two audiences:** anonymous visitors get a free draw-search page (SEO and acquisition); signed-in users get bond vaults, family tagging and alerts.
- **Draw data is global, bond data is private.** Draws, prize tiers and winning numbers are one shared, admin-verified dataset. Bonds, members and tags never leave their household.
- **Trust signals:** clear disclaimer that the app is not affiliated with National Savings (CDNS), a privacy policy, in-app account deletion and data export.
- **Scale target for v1:** 100k users, 20M tracked bonds, a full re-match of all bonds against a new draw in under 2 minutes.
- **Languages:** English and Urdu (RTL) from day one.

**Core features (v1)**

1. Draw ingestion from savings.gov.pk (txt, doc, pdf) with an admin verification queue.
2. Bond vault: single entry, range entry (123400–123499), CSV/Excel import, camera OCR on Android.
3. Family tagging: members, free-form tags, roles (Owner, Editor, Viewer) and invitations.
4. Automatic matching after each draw, with push, email and in-app alerts.
5. Dashboards: holdings by member, tag and denomination; win history; net prize after configurable withholding tax.
6. Draw calendar with reminders.

**Later (v2+):** premium tier (larger vaults, priority alerts, multi-household), WhatsApp alerts, public statistics pages, and a household audit export for tax filing.

## Roadmap

A small team (2 backend, 1 web, 1 Android) can reach a public launch in about 22 weeks. The draw engine comes first because every other feature depends on trustworthy results.

&#91;embedded content: roadmap · 8 phases, 5 gates\]

The web, Android and desktop phases run in parallel once the API is frozen at Gate C; slip in the draw engine moves everything after it.

## Phase breakdown

Eight phases, each ending in something you can demo and a gate you can test. Tick tasks off here as the team completes them.

### Phase 0 · Foundations (weeks 1–2)

**Goal:** a deployable skeleton that every later phase builds on.

- [ ] Create the monorepo, branch protection, PR template, CODEOWNERS
- [ ] Backend: uv project, Django 6.1, split settings (base/dev/prod/test), django-environ
- [ ] Docker compose: Postgres, Redis, api, worker, beat, Mailpit
- [ ] `core` app: UUID primary keys, timestamps, soft delete, `HouseholdScoped` base and manager
- [ ] Custom `User` model (email login, optional phone) before the first migration
- [ ] django-allauth headless: signup, email verification, password reset, TOTP MFA
- [ ] simplejwt with rotation and blacklist; `/api/v1/` routing; drf-spectacular docs
- [ ] `Household`, `Membership` with Owner / Editor / Viewer roles; django-rules predicates
- [ ] CI: ruff, mypy, pytest, migration check, OpenAPI export
- [ ] Sentry, structlog, health checks; staging environment deployed

**Deliverable:** a user can sign up, verify email, log in, and gets a personal household.

**Exit (Gate A):** CI green; tenant-isolation tests prove user A cannot read household B; staging deploy is one command.

### Phase 1 · Draw engine (weeks 3–6)

**Goal:** trustworthy draw results in the database, automatically.

- [ ] Models: `Denomination` (value, kind, `is_active`), `Draw`, `PrizeTier`, `WinningNumber`, `DrawSourceFile`
- [ ] Seed denominations and prize tiers; admin to edit them
- [ ] Fetcher: read the savings.gov.pk download page, list draws per denomination, download new files
- [ ] Store raw files in S3/R2 with SHA-256; skip files already imported
- [ ] Parsers as pure functions: `.txt`, `.pdf` (pdfplumber), `.doc` (LibreOffice to text), OCR fallback
- [ ] Tier detection: split first, second and third prize sections; normalize numbers to 6 digits
- [ ] Validators: expected winners per tier, no duplicates, numbers in range, draw number and date match
- [ ] Verification queue in admin: parsed draws wait as Pending until a Data Operator approves
- [ ] Manual upload path when the site changes or a file fails to parse
- [ ] Celery Beat: check daily, and every 30 minutes on draw days, until the file appears
- [ ] Backfill historical draws for every active denomination
- [ ] Public, anonymous draw search API and page (by denomination, draw, number), cached at the edge
- [ ] Parser regression suite: one real file per denomination and format

**Deliverable:** a new draw appears in the system within hours of publication, verified by a person.

**Exit (Gate B):** every denomination and format parses with correct tier counts; a broken file lands in the queue, never in published results.

### Phase 2 · Bonds and family (weeks 6–10)

**Goal:** households can load their bonds, tag them by family member, and are told when they win.

- [ ] Models: `Member` (a person in the household, with or without a login), `Bond`, `Tag`, `Win`
- [ ] Unique constraint on (household, denomination, number); index on (denomination, number) for matching
- [ ] Bond APIs: create, bulk create, update, soft delete, filter by member / tag / denomination
- [ ] Range entry (`123400–123499`) with a preview and a per-request cap
- [ ] CSV and Excel import as a background job, with a row-level error report
- [ ] Tags: create, rename, merge, bulk assign; a bond can carry many tags
- [ ] Invitations by email or link; accept flow; role changes; remove a member
- [ ] RBAC rules: Owner manages members and billing, Editor manages bonds, Viewer reads only
- [ ] Matcher: one set-based SQL join per verified draw, writes `Win` rows idempotently
- [ ] Re-match a household's bonds when they add bonds after a draw (checks past draws too)
- [ ] Notifications: FCM push, email, in-app inbox; per-user preferences and quiet hours
- [ ] Dashboard endpoints: holdings by member, tag and denomination; wins; net prize after configurable tax rate
- [ ] Draw calendar and reminder endpoints
- [ ] Audit log on bonds, tags, memberships and roles
- [ ] Data export (CSV/JSON) and account deletion endpoints
- [ ] Plan limits as settings (max bonds per household) so a premium tier can come later

**Deliverable:** through the API alone, a family can import 5,000 bonds, tag them per member, and receive a push when a verified draw matches.

**Exit (Gate C):** API v1 frozen and versioned; OpenAPI clients for TypeScript and Kotlin generate cleanly; matching 20M synthetic bonds against a draw finishes in under 2 minutes.

### Phase 3 · Web app (weeks 9–13)

**Goal:** the full product in a browser, which Electron reuses.

- [ ] Vite + React + TypeScript; TanStack Router and Query; Tailwind + shadcn/ui
- [ ] Generated API client in `packages/api-client`; auth with token refresh
- [ ] Screens: sign up / log in / MFA, onboarding, bond vault, add / range / import, members and tags, wins, draw calendar, settings
- [ ] Virtualized bond table with filters and bulk actions
- [ ] Household switcher and invitation acceptance
- [ ] English and Urdu with RTL layout; WCAG 2.2 AA checks
- [ ] Public pages: landing, draw search, privacy, terms (server-rendered or prerendered for SEO)
- [ ] Playwright suite for signup, import, tagging and a simulated win

**Deliverable:** web app on staging covering every Phase 2 feature.

### Phase 4 · Android app (weeks 11–18)

**Goal:** a native app that matches web and adds camera scanning and offline access.

- [ ] Modular project: `core/*` and `feature/*`; Hilt; Compose + Material 3
- [ ] Generated Retrofit client; tokens in Keystore-backed storage
- [ ] Same screens as web, plus Urdu RTL
- [ ] Room cache and WorkManager sync so the vault opens offline
- [ ] CameraX + ML Kit scanner: detect bond numbers, confirm, add in bulk
- [ ] FCM: win alerts deep-link to the win; draw reminders
- [ ] Crash reporting, ProGuard/R8, Play Integrity check on login
- [ ] Internal, then closed testing track on Google Play

**Deliverable:** signed build in closed testing with 20+ testers.

### Phase 5 · Desktop app (weeks 15–18)

**Goal:** Windows, macOS and Linux installers built from the web app.

- [ ] electron-vite shell loading the web build; `contextIsolation` on, `nodeIntegration` off
- [ ] Tokens in `safeStorage`; minimal preload API; strict CSP
- [ ] Native notifications for wins; tray icon; open-at-login option
- [ ] electron-builder with code signing and macOS notarization; electron-updater channels (beta, stable)

**Deliverable:** signed installers that auto-update from the release server.

**Exit (Gate D, covers phases 3–5):** every core flow works on web, Android and desktop; end-to-end suites green on all three.

### Phase 6 · Hardening and beta (weeks 19–22)

**Goal:** prove it is safe, fast and correct with real users before opening the doors.

- [ ] External penetration test; fix all high and critical findings
- [ ] Load tests with locust: matching, search, import, login under burst traffic
- [ ] Cloudflare WAF rules, rate limits, bot protection on signup and public search
- [ ] Backups and a full restore rehearsal in staging
- [ ] Runbooks: failed draw import, late draw file, push outage, database failover
- [ ] Privacy policy, terms and NSS disclaimer in English and Urdu
- [ ] Google Play data-safety form, store listing, screenshots; desktop download page
- [ ] Private beta: a few hundred households through at least one live draw
- [ ] Fix beta bugs; tune alert wording and onboarding from feedback

**Exit (Gate E):** every item in the public-launch checklist below is ticked.

### Phase 7 · Public launch and after (week 23 onward)

**Goal:** open signups and keep every draw import flawless.

- [ ] Production release on Play Store, web and desktop
- [ ] Staff an on-call rota for each draw day
- [ ] Product analytics (privacy-respecting): signups, bonds added, alert open rate
- [ ] Status page and in-app support channel

**Next releases, in priority order**

1. Premium tier: larger vaults, multiple households, priority alerts, payments (local gateway such as JazzCash or Easypaisa, plus cards)
2. WhatsApp and SMS win alerts
3. Public statistics pages: winning-number frequency by denomination, draw history
4. Claim assistant: checklist of documents and deadlines per prize, with reminders
5. iOS app

## Project structure

One monorepo, four clients of one API. The web app and Electron share a React codebase; Android is native Kotlin. API clients are generated from the OpenAPI schema, never hand-written.

```
bondtracker/
├── backend/                      # Django 6.1 API
│   ├── pyproject.toml            # managed with uv
│   ├── manage.py
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── dev.py
│   │   │   ├── prod.py
│   │   │   └── test.py
│   │   ├── urls.py
│   │   ├── asgi.py
│   │   ├── wsgi.py
│   │   └── celery.py
│   ├── apps/
│   │   ├── core/                 # base models (UUID, timestamps, soft delete),
│   │   │                         # tenant-scoped managers, pagination, exceptions
│   │   ├── accounts/             # User, auth, MFA, devices (FCM tokens), sessions
│   │   ├── households/           # Household, Member, Membership, Invitation, roles
│   │   ├── bonds/                # Bond, Tag, range + CSV import, OCR intake
│   │   │   ├── services/         # business logic (no logic in views)
│   │   │   └── selectors/        # read queries
│   │   ├── draws/                # Denomination, Draw, PrizeTier, WinningNumber
│   │   │   └── ingestion/
│   │   │       ├── fetchers.py   # savings.gov.pk listing + downloads
│   │   │       ├── parsers/
│   │   │       │   ├── txt.py
│   │   │       │   ├── pdf.py
│   │   │       │   └── doc.py    # LibreOffice headless -> text
│   │   │       ├── validators.py # tier counts, duplicates, checksums
│   │   │       └── tasks.py
│   │   ├── matching/             # set-based SQL matcher, Win records
│   │   ├── notifications/        # push, email, in-app; preferences
│   │   ├── billing/              # plans, limits (phase 7)
│   │   ├── audit/                # audit log views, data export, deletion
│   │   └── public/               # anonymous draw search, SEO pages
│   ├── api/
│   │   └── v1/
│   │       ├── urls.py           # routers per app
│   │       ├── permissions.py    # RBAC rules
│   │       └── throttles.py
│   ├── templates/                # emails, public pages
│   ├── locale/                   # en, ur
│   └── tests/
│       ├── fixtures/draws/       # real txt/doc/pdf files for parser tests
│       ├── factories.py
│       └── ...
├── web/                          # React + TypeScript (Vite)
│   ├── src/
│   │   ├── app/                  # router, providers, layout
│   │   ├── features/
│   │   │   ├── auth/
│   │   │   ├── bonds/
│   │   │   ├── household/
│   │   │   ├── draws/
│   │   │   └── dashboard/
│   │   ├── components/ui/        # shadcn/ui
│   │   ├── lib/                  # api client wrapper, i18n, utils
│   │   └── locales/{en,ur}/
│   └── package.json
├── desktop/                      # Electron shell around web/
│   ├── src/main/                 # main process, auto-update, secure storage
│   ├── src/preload/              # contextBridge, minimal API surface
│   └── electron-builder.yml
├── android/                      # Kotlin + Jetpack Compose
│   ├── app/
│   ├── core/{network,database,datastore,ui,model}/
│   ├── feature/{auth,bonds,household,draws,scan,dashboard}/
│   └── build-logic/              # convention plugins
├── packages/
│   └── api-client/               # generated TypeScript client
├── infra/
│   ├── docker/                   # Dockerfiles (api, worker, web)
│   ├── compose.yaml              # local stack
│   ├── deploy/                   # Kamal or Kubernetes manifests
│   └── monitoring/
├── docs/
│   ├── adr/                      # architecture decision records
│   └── runbooks/
└── .github/workflows/            # CI per package + release pipelines
```

**Rules that keep it enterprise-grade**

- Views stay thin: services write, selectors read, serializers only validate and shape.
- Every household-owned model inherits a `HouseholdScoped` base whose manager refuses unscoped queries.
- Draw parsers are pure functions (bytes in, rows out) so they are tested against real files.
- The OpenAPI schema is committed; CI fails if the generated clients drift from it.

## Backend libraries

Python 3.14 on Django 6.1, the current feature release (out since August 2026). Use its model field fetch modes to stop N+1 queries and its database-level `on_delete` options for cascades on large bond tables.

| Area | Library | Use it for |
| --- | --- | --- |
| Core | Django 6.1 | ORM, admin, migrations, built-in CSP |
| Core | psycopg 3 (`psycopg[binary,pool]`) | PostgreSQL driver with connection pooling |
| API | djangorestframework | REST API for all clients |
| API | drf-spectacular | OpenAPI 3 schema and Swagger/Redoc docs |
| API | django-filter | Filtering bonds, draws and wins |
| API | django-cors-headers | CORS for the web app |
| Auth | django-allauth (headless mode) | Signup, email/phone verification, social login, MFA (TOTP, passkeys) |
| Auth | djangorestframework-simplejwt | Access/refresh tokens with rotation and blacklist for mobile and desktop |
| Auth | argon2-cffi | Argon2 password hashing |
| Auth | django-axes | Brute-force login lockout |
| RBAC | django-rules | Object-level permissions (can this member edit this household's bonds?) |
| Background jobs | celery + django-celery-beat | Scraping, parsing, matching, scheduled checks after draw dates |
| Background jobs | redis (redis-py) + django-redis | Broker, cache, rate-limit counters |
| Ingestion | httpx | Fetching the savings.gov.pk listing and files |
| Ingestion | selectolax | Fast HTML parsing of the download page |
| Ingestion | pdfplumber + pypdfium2 | Text and layout extraction from PDFs |
| Ingestion | LibreOffice (headless, system package) | Converting legacy .doc files to text |
| Ingestion | python-docx | Reading .docx when NSS publishes it |
| Ingestion | pytesseract | OCR fallback for scanned PDFs |
| Import/export | openpyxl | Excel bond import and export |
| Notifications | fcm-django (firebase-admin) | Android push |
| Notifications | django-anymail | Transactional email via SES, Postmark or Mailgun |
| Storage | django-storages + boto3 | Raw draw files and exports on S3 or Cloudflare R2 |
| Storage | whitenoise | Static files |
| Audit | django-auditlog | Who changed which bond or role, and when |
| Security | django-encrypted-model-fields or Fernet (cryptography) | Encrypting CNIC and phone numbers at rest |
| Ops | gunicorn + uvicorn workers | ASGI serving |
| Ops | sentry-sdk | Error tracking |
| Ops | opentelemetry-instrumentation-django | Tracing |
| Ops | django-health-check | Liveness/readiness probes |
| Ops | structlog | JSON logs |
| Config | django-environ | 12-factor settings from env vars |

**Dev and quality**

| Library | Use it for |
| --- | --- |
| uv | Dependency and Python version management |
| ruff | Lint and format |
| mypy + django-stubs + djangorestframework-stubs | Type checking |
| pytest-django, pytest-cov, factory-boy | Tests |
| hypothesis | Property tests for the parsers and range input |
| locust | Load tests on match and search endpoints |
| pip-audit, bandit | Dependency and code security scans |
| pre-commit | Run all of the above before each commit |

## Frontend libraries

Build the web app once in React + TypeScript and ship it in Electron for desktop. Build Android natively in Kotlin + Jetpack Compose, because camera OCR, background sync and push are first-class there.

**Web (React SPA)**

| Library | Use it for |
| --- | --- |
| React + TypeScript + Vite | App framework and build |
| TanStack Router | Type-safe routing |
| TanStack Query | Server state, caching, retries |
| TanStack Table + TanStack Virtual | Large bond lists (thousands of rows) |
| Tailwind CSS + shadcn/ui (Radix) | Accessible components and styling |
| react-hook-form + zod | Forms and validation (bond ranges, imports) |
| openapi-typescript + openapi-fetch | Typed API client generated from the schema |
| i18next + react-i18next | English and Urdu, RTL layout |
| Recharts | Holdings and win charts |
| date-fns | Draw dates and countdowns |
| Papa Parse / SheetJS | Client-side CSV and Excel preview before upload |
| Sentry (browser SDK) | Error tracking |
| Vitest + Testing Library + Playwright | Unit, component and end-to-end tests |
| ESLint + Prettier | Lint and format |

**Desktop (Electron)**

| Library | Use it for |
| --- | --- |
| Electron + electron-vite | Shell and build around the web app |
| electron-builder | Signed installers for Windows, macOS, Linux |
| electron-updater | Auto-update from GitHub Releases or S3 |
| safeStorage (built into Electron) | Keeping refresh tokens in the OS keychain |
| electron-log | Local logs for support |

Harden it: `contextIsolation` on, `nodeIntegration` off, a minimal preload API, and a strict CSP.

**Android (Kotlin)**

| Library | Use it for |
| --- | --- |
| Jetpack Compose + Material 3 | UI |
| Navigation Compose | Screens and deep links from push alerts |
| Hilt | Dependency injection |
| Retrofit + OkHttp + kotlinx.serialization | Networking, generated from OpenAPI via openapi-generator |
| Room | Offline cache of bonds and draws |
| Paging 3 | Large bond lists |
| WorkManager | Background sync and retrying imports |
| DataStore + Android Keystore | Settings and encrypted token storage |
| CameraX + ML Kit Text Recognition | Scanning bond numbers with the camera |
| Firebase Cloud Messaging | Win alerts and draw reminders |
| Coil | Images |
| Firebase Crashlytics or Sentry | Crash reporting |
| JUnit, Turbine, Compose UI Test | Tests |
| Detekt + ktlint | Static analysis and format |

## Infrastructure and DevOps

Start on containers with managed Postgres and Redis; move to Kubernetes only when one VM per service stops being enough.

| Area | Choice | Notes |
| --- | --- | --- |
| Database | PostgreSQL (managed: RDS, Cloud SQL, Neon or DigitalOcean) | Partition `winning_number` by denomination; unique index on (denomination, number) for matching |
| Cache and broker | Redis or Valkey | Separate logical DBs for cache, broker and throttling |
| Containers | Docker, multi-stage builds | Separate images for api, worker, beat |
| Deploy | Kamal (simple) or Kubernetes + Helm (scale) | Zero-downtime deploys, migrations as a release step |
| Edge | Cloudflare (DNS, WAF, CDN, rate limiting) | Caches the public draw-search pages |
| Reverse proxy | Caddy or Nginx | TLS, gzip, request limits |
| Object storage | S3 or Cloudflare R2 | Raw draw files, exports, backups |
| CI/CD | GitHub Actions | Per-package pipelines, schema drift check, store and installer releases |
| Secrets | Doppler, AWS Secrets Manager or GitHub OIDC | No secrets in the repo |
| Monitoring | Sentry + Grafana (Prometheus, Loki, Tempo) or Better Stack | Alert on failed ingestion, slow matching, error spikes |
| Uptime | Better Stack or UptimeRobot | Public status page |
| Backups | Daily Postgres snapshots + point-in-time recovery | Restore drill every quarter |

**Environments:** local (compose), staging (mirrors prod, synthetic data), production. Every pull request runs lint, type checks, tests, a migration check and an OpenAPI diff.

## Public-launch checklist

Nothing ships publicly until every box below is ticked.

**Security**

- [ ] Third-party penetration test of API, web and Android app
- [ ] OWASP ASVS level 2 review; OWASP MASVS for Android
- [ ] MFA available for all users, required for admins and data operators
- [ ] Per-user and per-IP throttling on login, OTP, search and import endpoints
- [ ] Tenant-isolation tests: a user can never read another household's bonds
- [ ] Encryption at rest for CNIC and phone numbers; TLS everywhere
- [ ] Dependency scanning and secret scanning in CI

**Legal and trust**

- [ ] Privacy policy and terms of service, in English and Urdu
- [ ] "Not affiliated with National Savings / CDNS" disclaimer on every results screen
- [ ] Results labelled "verify with the official list before claiming"
- [ ] Check the status of Pakistan's personal data protection law at launch and comply with it
- [ ] Data export and account deletion, in-app and by web link

**Store and distribution**

- [ ] Google Play: data safety form, account-deletion link, target the latest required API level
- [ ] Signed Windows and macOS installers (code signing, notarization)
- [ ] Store listing, screenshots and support email

**Data quality and scale**

- [ ] Parser regression suite over at least one real file per denomination and format
- [ ] Admin verification step before any draw is published
- [ ] Load test: full re-match of 20M bonds in under 2 minutes; p95 API under 300 ms
- [ ] Backups restored successfully in staging
- [ ] On-call runbook for a failed or late draw import

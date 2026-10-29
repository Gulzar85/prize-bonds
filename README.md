# Prize Bond Tracker

A public, multi-tenant app for Pakistani households to track National Savings prize bonds, tag them by family member, and get alerted automatically when a bond wins.

## Features (Phase 0 - Current)

- Multi-tenant architecture (Household-based isolation)
- Custom User model with email authentication
- Email verification with django-allauth
- TOTP MFA support
- JWT authentication for API clients (allauth headless built-in strategy, see ADR 0004)
- Role-based access control (OWNER, EDITOR, VIEWER)
- Tenant isolation enforced at all levels
- Comprehensive security (CSP, HSTS, Argon2, etc.)

## Phase 1 - Draw engine

Discovers, downloads, parses, validates and (after human review) publishes every National Savings prize bond draw from
savings.gov.pk, and serves it through a public anonymous API.

- Review queue, review screen and manual upload: Django admin > Draws > Draw revisions (`data_operator` group + MFA).
- Public API (no auth, throttled, cached 5 minutes): `GET /api/v1/public/denominations/`, `draws/`, `draws/{id}/`,
  `draws/{id}/numbers/?tier=`, `POST check/` (50 numbers or 5 ranges of at most 1,000). Every response carries a disclaimer.
- Backfill history: `python manage.py backfill_draws --dry-run` first, then without `--dry-run`
  (`--denomination SLUG`, `--since YEAR`, `--approve-clean --as EMAIL`).
- Celery: a dedicated `ingestion` queue and worker (see `infra/compose.yaml`). Beat runs discovery daily at 09:10 Asia/Karachi,
  draw-day polling every 30 minutes from 12:00 to 23:30, a weekly revision watch and the watchdogs.
- Docs: [source survey](docs/research/nss-source-survey.md), ADRs 0006-0008, [draw-day runbook](docs/runbooks/draw-day.md).
- Optional system tools for non-text sources: Tesseract (scanned PDFs) and LibreOffice (`.doc`).

## Quick Start

### Prerequisites
- Python 3.14
- PostgreSQL 17+
- Redis
- [uv](https://docs.astral.sh/uv/) for dependency management

### Local Development with Docker

1. Copy environment variables:
```bash
cp .env.example .env
```

2. Start all services:
```bash
make up
```

3. Run migrations:
```bash
make migrate
```

4. Create a superuser:
```bash
make createsuperuser
```

5. Access the API:
- API: http://localhost:8000/api/v1/
- Swagger UI: http://localhost:8000/api/v1/schema/swagger-ui/
- Admin: http://localhost:8000/admin/
- Health: http://localhost:8000/health/ready/

### Without Docker

```bash
cd backend && uv sync
DJANGO_SETTINGS_MODULE=config.settings.test uv run pytest   # in-memory SQLite unless DATABASE_URL is set
```

Auth endpoints for native clients live under `/api/v1/auth/app/v1/` (signup, email verification, login,
`tokens/refresh`, TOTP and recovery codes); their OpenAPI spec is at `/api/v1/auth/openapi.yaml`.
Set `JWT_PRIVATE_KEY` (RSA PEM) in `.env`; generate one with
`openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048`.

## Development Commands

```bash
make up          # Start all services (infra/compose.yaml)
make down        # Stop all services
make build       # Build images
make test        # Run tests with coverage
make lint        # Run ruff linting
make format      # Run ruff formatting
make typecheck   # Run mypy
make migrate     # Run migrations
make makemigrations # Create migrations
make shell       # Django shell
make logs        # View logs
make schema      # Export OpenAPI schema
```

## Architecture

See [docs/adr/](docs/adr/) for architecture decision records.

## License

Proprietary - All rights reserved

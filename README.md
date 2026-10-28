# Prize Bond Tracker

A public, multi-tenant app for Pakistani households to track National Savings prize bonds, tag them by family member, and get alerted automatically when a bond wins.

## Features (Phase 0 - Current)

- Multi-tenant architecture (Household-based isolation)
- Custom User model with email authentication
- Email verification with django-allauth
- TOTP MFA support
- JWT authentication for API clients
- Role-based access control (OWNER, EDITOR, VIEWER)
- Tenant isolation enforced at all levels
- Comprehensive security (CSP, HSTS, Argon2, etc.)

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

## Development Commands

```bash
make up          # Start all services
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

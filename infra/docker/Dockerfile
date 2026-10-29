# syntax=docker/dockerfile:1
# Build context is the repository root (see infra/compose.yaml).
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1     PATH="/app/.venv/bin:$PATH"     DJANGO_SETTINGS_MODULE=config.settings.prod

WORKDIR /app

# The ingestion worker also needs Tesseract (scanned PDFs) and LibreOffice (.doc); other images stay slim.
ARG INSTALL_INGESTION_TOOLS=0
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && if [ "$INSTALL_INGESTION_TOOLS" = "1" ]; then \
         apt-get install -y --no-install-recommends tesseract-ocr libreoffice-writer; \
       fi \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 app

COPY --from=builder /app/.venv /app/.venv
COPY --chown=app:app backend /app

# Static files need settings to import; these values are build-time placeholders only.
RUN SECRET_KEY=build-only DATABASE_URL=sqlite:///:memory: python manage.py collectstatic --noinput     && chown -R app:app /app/staticfiles

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3     CMD curl -fsS http://localhost:8000/health/live/ || exit 1

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4"]

# Multi-stage build using uv
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

WORKDIR /app

# Install dependencies
COPY backend/pyproject.toml backend/uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

# Final stage
FROM python:3.14-slim-bookworm

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 app && chown -R app:app /app

# Copy virtual environment
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application
COPY backend /app
RUN chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/live/ || exit 1

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]

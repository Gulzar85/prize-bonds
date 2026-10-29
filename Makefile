.PHONY: up down build test lint format typecheck migrate makemigrations shell logs schema createsuperuser collectstatic clean

up:
	docker compose -f infra/compose.yaml up -d

down:
	docker compose -f infra/compose.yaml down

build:
	docker compose -f infra/compose.yaml build

test:
	cd backend && uv run pytest --cov --cov-fail-under=90

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .

format:
	cd backend && uv run ruff format .

typecheck:
	cd backend && uv run mypy apps api

migrate:
	cd backend && uv run python manage.py migrate

makemigrations:
	cd backend && uv run python manage.py makemigrations

shell:
	cd backend && uv run python manage.py shell

logs:
	docker compose -f infra/compose.yaml logs -f

schema:
	cd backend && DJANGO_SETTINGS_MODULE=config.settings.test uv run python manage.py spectacular --file openapi.yaml --validate --fail-on-warn

createsuperuser:
	cd backend && uv run python manage.py createsuperuser

collectstatic:
	cd backend && uv run python manage.py collectstatic --noinput

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	docker compose -f infra/compose.yaml down -v

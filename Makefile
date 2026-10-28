.PHONY: up down build test lint format typecheck migrate makemigrations shell logs schema createsuperuser collectstatic clean

up:
	docker compose -f infra/compose.yaml up -d

down:
	docker compose -f infra/compose.yaml down

build:
	docker compose -f infra/compose.yaml build

test:
	cd backend && pytest

lint:
	cd backend && ruff check .

format:
	cd backend && ruff format .

typecheck:
	cd backend && mypy .

migrate:
	cd backend && python manage.py migrate

makemigrations:
	cd backend && python manage.py makemigrations

shell:
	cd backend && python manage.py shell

logs:
	docker compose -f infra/compose.yaml logs -f

schema:
	cd backend && python manage.py spectacular --file ../openapi.yaml

createsuperuser:
	cd backend && python manage.py createsuperuser

collectstatic:
	cd backend && python manage.py collectstatic --noinput

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	docker compose -f infra/compose.yaml down -v

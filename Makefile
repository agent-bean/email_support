.PHONY: setup check generate check-api-drift up down database-up database-check database-down backend-setup backend-check backend-database-check backend-generate web-setup web-check web-generate dev-api dev-web

setup: backend-setup web-setup

check: backend-check web-check

generate: backend-generate web-generate

check-api-drift:
	./scripts/check-api-drift.sh

up:
	docker compose up --detach --build --wait --wait-timeout 60

down:
	docker compose down --remove-orphans

database-up:
	./scripts/check-database.sh up

database-check:
	./scripts/check-database.sh local tests/database

database-down:
	./scripts/check-database.sh down

backend-setup:
	cd apps/backend && uv sync --locked

backend-check:
	cd apps/backend && uv lock --check
	cd apps/backend && uv run --locked pytest -q tests/unit tests/integration tests/contracts
	cd apps/backend && uv run --locked ruff check .
	cd apps/backend && uv run --locked ruff format --check .
	cd apps/backend && uv run --locked mypy --strict src scripts tests migrations evals
	@if [ "$${CI:-}" = "true" ]; then $(MAKE) backend-database-check; fi

backend-database-check:
	@if [ "$${CI:-}" = "true" ]; then ./scripts/check-database.sh ci tests/database; else ./scripts/check-database.sh local tests/database; fi

backend-generate:
	cd apps/backend && uv run --locked python scripts/export-openapi.py

web-setup:
	cd apps/web && npm ci

web-check:
	cd apps/web && npm run test
	cd apps/web && npm run typecheck
	cd apps/web && npm run lint
	cd apps/web && npm run format:check
	cd apps/web && npm run build

web-generate:
	cd apps/web && npm run generate:api

dev-api:
	cd apps/backend && uv run --locked uvicorn email_support.main:app --host 127.0.0.1 --port 8000

dev-web:
	cd apps/web && npm run dev

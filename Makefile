.PHONY: backend-setup backend-check backend-generate dev-api

backend-setup:
	cd apps/backend && uv sync --locked

backend-check:
	cd apps/backend && uv lock --check
	cd apps/backend && uv run --locked pytest -q tests/test_health.py tests/test_openapi.py
	cd apps/backend && uv run --locked ruff check .
	cd apps/backend && uv run --locked ruff format --check .
	cd apps/backend && uv run --locked mypy --strict src scripts tests

backend-generate:
	cd apps/backend && uv run --locked python scripts/export-openapi.py

dev-api:
	cd apps/backend && uv run --locked uvicorn email_support.main:app --host 127.0.0.1 --port 8000

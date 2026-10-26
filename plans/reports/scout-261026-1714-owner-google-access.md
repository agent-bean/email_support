# Issue 5/6 planning scout

Verified 2026-10-26, Asia/Bangkok. Planning only: `--hard --tdd --yagni`.

## Existing evidence

| Evidence | Verified implication |
| --- | --- |
| `apps/backend/src/email_support/main.py:5` | Only health router is composed; no protected routes/auth resources exist. |
| `apps/backend/src/email_support/api/health.py:11` | Existing public liveness is `/api/health`, not `/health`. |
| `apps/backend/src/email_support/storage/postgres/persistence/database.py:11` | Async engine creation is lazy; reuse session factory/disposal, not another DB abstraction. |
| `apps/backend/src/email_support/models/persistence/core.py:31` | Provider account identity exists, not an owner/session/token contract. |
| `apps/backend/src/email_support/storage/postgres/persistence/tables/core.py:32` | Stable provider-account IDs namespace mail/meetings; disconnect must preserve referenced rows. |
| `apps/backend/src/email_support/storage/postgres/persistence/tables/__init__.py:3` | Alembic metadata facade must import new access/connection mappings. |
| `apps/backend/migrations/env.py:11` | Migration metadata comes from that facade, not API startup. |
| `apps/backend/pyproject.toml:10` | Production dependencies currently lack OAuth/encryption/HTTP clients. |
| `apps/backend/pyproject.toml:22` | `httpx2` is currently dev-only; OAuth needs a production dependency. |
| `apps/backend/pyproject.toml:33` | Normal pytest discovery excludes real database tests deliberately. |
| `apps/backend/tests/database/conftest.py:42` | Reuse function-scoped guarded DB targets/backups/cleanup for auth storage tests. |
| `apps/backend/tests/database/migrations/test_migrations.py:32` | Empty install, preservation, restore tests currently assert the old head; update for additive revisions without dropping preservation coverage. |
| `apps/backend/tests/contracts/test_openapi.py:25` | Export uses subprocess and rewrites snapshot; import/export must stay credential-free. |
| `apps/web/src/app/App.tsx:4` | Web currently renders health only; no access/connection features exist. |
| `apps/web/src/shared/api/health.ts:12` | Generated SDK calls explicitly validate responses and propagate caller cancellation/deadline. Preserve these properties. |
| `apps/web/playwright.config.ts:5` | Only `health-smoke.spec.ts` is discovered; merely adding E2E files does not execute them. |
| `apps/web/tests/e2e/health-smoke.spec.ts:3` | Existing browser smoke verifies real API through same-origin proxy without Google credentials. |
| `compose.yaml:1` | Default local stack has API/web only; auth requires explicit runtime DB/config route, separate from disposable test DB. |
| `compose.test.yaml:1` | Test PostgreSQL is guarded and isolated; do not reuse its credentials/data as application runtime storage. |
| `Makefile:30` | Existing backend check includes tests/lint/format/mypy; real DB check runs in Backend CI. |
| `Makefile:47` | Existing web check includes unit tests/type/lint/format/build. |
| `scripts/check-api-drift.sh:12` | Drift check rejects dirty generated paths before generation; run after intentional generation and clean committed generated state. |
| `.github/workflows/ci.yml:120` | Existing Smoke job starts default Compose and runs browser smoke, then stops the stack. |

Live GitHub checked with `gh issue view` and dependency REST endpoints: #5 and #6 open; #5 blocked-by #3 closed; #6 blocked-by #5 open. Original acceptance criteria include live Google smoke for #6. Existing historical plan status prose is not current Issue authority.

## Ownership and scope

Reuse canonical storage, schema metadata, migration/database harness and generated contracts. New access/Google integration/service/persistence/web feature boundaries are justified by real responsibilities. More than eight files are expected because contracts, schema, API, UI and behavior tests are all required; no generic repositories, base services, Redis, worker, sync, send execution or production deployment belong here.

One plan coordinates three sequential phases. Issue #5 is independently reviewable after phases 1–2; phase 3 delivers #6. Shared main/config/migration facade/OpenAPI/App/runtime/doc files transfer ownership sequentially. No application commands or tests were run during scouting. One guessed browser-test filename was absent; the actual existing file is `health-smoke.spec.ts` and is used throughout the plan.

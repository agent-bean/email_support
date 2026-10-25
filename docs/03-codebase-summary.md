# Codebase Summary

This page is a navigation guide for future contributors and coding agents. For the accepted module relationships and rationale, see [System Architecture](02-system-architecture.md). For typing, naming, and quality expectations, see [Code Standards](04-code-standards.md).

## Backend entry points

Backend paths below are relative to `apps/backend/`; web paths are relative to `apps/web/`.

- `src/email_support/main.py` composes the current FastAPI application. The implemented `/api/health` route is in `src/email_support/api/health.py`, with its Pydantic `StrEnum` contract in `src/email_support/models/health.py`.
- `src/email_support/models/persistence/` groups typed canonical contracts by core, decisions and projections, with a stable package facade. The PostgreSQL adapter is grouped under `src/email_support/storage/postgres/persistence/`: async session setup, caller-owned storage operations, and scope-grouped SQLAlchemy mappings under `tables/`. The API does not yet connect to this storage.
- `migrations/versions/` contains the additive canonical-core and approval/knowledge revisions. `tests/database/` verifies migrations and storage against PostgreSQL; the guarded runner is [`scripts/check-database.sh`](../scripts/check-database.sh) and its backup/restore helpers are in `scripts/test_database.py`.
- `scripts/export-openapi.py` writes the offline OpenAPI contract to `openapi.json`; `tests/unit/` groups model, persistence-contract, and database-guard tests by scope; `tests/integration/` covers the HTTP endpoint, and `tests/contracts/` covers the exported OpenAPI contract.
- `src/email_support/worker.py` is the planned worker composition point; background company briefing work belongs under `workflows/company_briefing/`.
- Shared product and persistence contracts belong in `models/`. PostgreSQL ORM mappings and queries belong under `storage/postgres/`; do not use ORM rows as API or workflow contracts.

The intended backend boundaries are:

- `api/` — HTTP routes and request dependencies.
- `workflows/company_briefing/` — graph, workflow state, and nodes.
- `agents/` — role instructions, context, and tool allowlists.
- `tools/` — typed functions exposed to models.
- `services/` — business invariants, transaction coordination, approvals, delivery, synchronization, and knowledge operations.
- `integrations/` — provider SDKs and protocols for Gmail, Google Calendar, Tavily, LLMs, and embeddings.
- `storage/` — persistence adapters, organized by backend.
- `models/` — application, API, tool, and LLM input/output contracts.
- `core/` — configuration and telemetry.

Use the architecture page for dependency direction and cross-boundary decisions. Do not create empty folders to match this map; add a boundary when implementation gives it a real owner.

## Web entry points

`src/main.tsx` mounts the current web app. `src/app/App.tsx` renders the health query's loading, healthy, and error states. `src/shared/api/health.ts` calls the generated SDK with caller cancellation and a bounded deadline. `openapi-ts.config.ts` owns generation into `src/shared/api/generated/`; do not hand-edit that directory.

`vite.config.ts` owns the same-origin `/api` proxy and local web port. Root `compose.yaml` runs only the API and web services for local development; its published ports bind to loopback. Web unit tests live in `tests/unit/`, while the real-browser smoke lives in `tests/e2e/`.

Product-specific code is planned to group by feature (`access`, `connections`, `research`, `briefings`, `companies`, and `knowledge`). A feature may contain `api/`, `model/`, `hooks/`, or `ui/` only where those responsibilities exist. Cross-feature contracts and generated API access belong under `src/shared/api/`; reusable presentation components belong under `src/shared/ui/`.

Keep feature internals private to their feature. The architecture page records the intended web dependency boundaries and server-state ownership.

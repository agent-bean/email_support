# Codebase Summary

This page is a navigation guide for future contributors and coding agents. For the accepted module relationships and rationale, see [System Architecture](02-system-architecture.md). For typing, naming, and quality expectations, see [Code Standards](04-code-standards.md).

## Backend entry points

Backend paths below are relative to `apps/backend/`; web paths are relative to `apps/web/`.

- `src/email_support/main.py` is the planned HTTP application composition point; begin HTTP work at `api/` and move domain decisions into `services/`.
- `src/email_support/worker.py` is the planned worker composition point; background company briefing work belongs under `workflows/company_briefing/`.
- Shared product contracts belong in `models/`. PostgreSQL ORM mappings and queries belong under `storage/postgres/`; do not use ORM rows as API or workflow contracts.

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

The planned web application starts at `src/app/` for routing and providers. Product-specific code is grouped by feature (`access`, `connections`, `research`, `briefings`, `companies`, and `knowledge`). A feature may contain `api/`, `model/`, `hooks/`, or `ui/` only where those responsibilities exist. Cross-feature contracts and generated API access belong under `src/shared/api/`; reusable presentation components belong under `src/shared/ui/`.

Keep feature internals private to their feature. The architecture page records the intended web dependency boundaries and server-state ownership.

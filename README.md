# Email Support

A single-owner assistant for preparing sourced company briefings from business email and meeting context, with explicit human approval for delivery and knowledge reuse.

## Current status

The repository has a credential-free FastAPI health endpoint, a minimal web client with a generated and runtime-validated API contract, a two-service local Compose stack, and pull request/main CI. Authentication, provider integrations, storage, the worker, and production deployment are not implemented.

## Local development

Use Python 3.13.17 with uv 0.13.5, and Node 24.22.1 with npm 12.2.1. Application checks and the health slice do not need provider credentials or external services.

```sh
make setup
make check
make generate
make check-api-drift
```

Run the backend and web dev servers in separate terminals with `make dev-api` and `make dev-web`, then open <http://127.0.0.1:5173>. To use the local container stack instead, run `make up`; stop it with `make down`.

The browser smoke test uses Chromium. Install it from `apps/web/` with `npx playwright install chromium`, start the local stack with `make up`, run `npm --prefix apps/web run test:smoke`, and finish with `make down`.

`make generate` intentionally rewrites the committed OpenAPI and web SDK artifacts. `make check-api-drift` checks those paths before generation and reports committed drift afterward.

## Planned capabilities

- Synchronize Gmail and read Google Calendar to identify relevant company and meeting context.
- Produce editable, source-cited Markdown briefings using bounded web research and reusable approved knowledge.
- Require approval of the exact briefing version, action, and recipients before sending email or saving knowledge.
- Retrieve approved knowledge through relationship queries and semantic search.
- Add PDF/Word export and attachment ingestion as separate increments.

The planned stack uses FastAPI, LangGraph, and a Python worker for the backend; React, TypeScript, and Vite for the web app; and PostgreSQL, Neo4j, and Qdrant for storage and retrieval.

## Documentation

Start with the [documentation index](docs/00-index.md) for product scope, architecture, code conventions, deployment direction, and the delivery roadmap.

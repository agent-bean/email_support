# Email Support

A single-owner assistant for preparing sourced company briefings from business email and meeting context, with explicit human approval for delivery and knowledge reuse.

## Current status

The repository has a credential-free FastAPI health endpoint, typed PostgreSQL persistence for canonical records, approvals, knowledge, and projection metadata, and owner Google sign-in plus Google Workspace connection flows with PostgreSQL-backed state when explicitly configured. The web client includes owner access and connection states while keeping health public. Default Compose and CI remain credential-free; Google access is unavailable there until the opt-in local runtime is configured. Automated Gmail/Calendar workflows, the worker, and production deployment are not implemented.

## Local development

Use Python 3.13.17 with uv 0.13.5, and Node 24.22.1 with npm 12.2.1. Application checks and the health slice do not need provider credentials or external services.

```sh
make setup
make check
make generate
make check-api-drift
```

`make check` and `make check-api-drift` do not require PostgreSQL. `make generate` intentionally rewrites the committed OpenAPI and web SDK artifacts; `make check-api-drift` checks those paths before generation and reports committed drift afterward.

Run the backend and web dev servers in separate terminals with `make dev-api` and `make dev-web`, then open <http://127.0.0.1:5173>. To use the local container stack instead, run `make up`; stop it with `make down`.

The browser smoke test uses Chromium. Install it from `apps/web/` with `npx playwright install chromium`, start the local stack with `make up`, run `npm --prefix apps/web run test:smoke`, and finish with `make down`.

To exercise owner sign-in locally, configure the separate opt-in runtime described in [Local authenticated development](docs/06-deployment-guide.md#local-authenticated-development). It uses its own persistent PostgreSQL data and verified backups under ignored `.local-auth/`; it cannot share the test database. OAuth must be configured with the loopback callback and origin before login can succeed.

## PostgreSQL persistence verification

Run the real-database migrations, storage, backup, and restore checks with Docker Compose:

```sh
make database-check
```

The test service binds to `127.0.0.1:55432`. `make database-up` starts it for manual development; `make database-down` verifies and cleans owned test targets before stopping it. Local test data and private credentials remain under the ignored `.test-database/` directory. Failed runs stop the owned service and retain recovery files there; successful checks remove only that run's archives. Backend CI uses its own job-scoped PostgreSQL service and discards it with the job. These test routes do not configure production database access or backups.

## Planned capabilities

- Synchronize Gmail and read Google Calendar to identify relevant company and meeting context.
- Produce editable, source-cited Markdown briefings using bounded web research and reusable approved knowledge.
- Require approval of the exact briefing version, action, and recipients before sending email or saving knowledge.
- Retrieve approved knowledge through relationship queries and semantic search.
- Add PDF/Word export and attachment ingestion as separate increments.

The broader application plan adds LangGraph and a Python worker, plus Neo4j and Qdrant for graph and semantic projections.

## Documentation

Start with the [documentation index](docs/00-index.md) for product scope, architecture, code conventions, deployment direction, and the delivery roadmap.

# Issue #3 planning scout

Baseline: `0c3c669fe9c81575952b55ddbce9302c2e20539d`, branch `docs/issue-3-persistence-plan`. Planning only: `--tdd --hard --yagni`.

## Confirmed implementation

- `apps/backend/src/email_support/main.py:7` composes FastAPI with the health router only. No database startup or API storage consumer exists.
- `apps/backend/pyproject.toml:10` lists FastAPI, Pydantic and Uvicorn; SQLAlchemy, Alembic, a PostgreSQL driver and async test support are not installed project dependencies yet.
- `apps/backend/pyproject.toml:28` discovers all tests; `Makefile:23` runs the entire backend test tree. Any new database tests must preserve credential-free existing checks or explicitly change command ownership and all callers.
- `apps/backend/tests/integration/test_health_endpoint.py:16` proves the existing HTTP health contract. `apps/backend/tests/unit/test_health_model.py:7` tests validation; `apps/backend/tests/contracts/test_openapi.py:23` runs offline export twice. An initial lookup used the wrong filename `test_health.py`; discovery resolved the real path above.
- `Makefile:18` owns backend setup; `Makefile:21` owns tests, Ruff and strict mypy. Existing `make check`, `make check-api-drift`, `make up`, and `make down` are real commands; database-specific commands will be new proposed tooling.
- `compose.yaml:2` and `compose.yaml:17` define API and web only; no persistence volume or database exists in the manifest.
- `.github/workflows/ci.yml:13` defines Backend, which calls `make backend-check` at line 28. API contracts calls setup and drift checks; Smoke calls `make up` and `make down`. Keep existing check names and read-only permissions.
- `.gitignore` ignores environment files but currently has no backup directory rule. Never commit DSNs, dumps, or database contents.

## Scope and design boundaries

The live Issue #3 was OPEN/Ready when read. Its only recorded prerequisite, Issue #2, is closed. The issue requires all listed canonical record families, migration preservation, database integrity, typed persistence and rollback, provenance, explicit missing values, UTC timestamps and immutable versions. It does not authorize provider adapters, authentication, workers, LangGraph checkpoints, CRUD routes/screens, or projection execution.

The accepted architecture in `docs/02-system-architecture.md` owns PostgreSQL truth and rebuildable projections. `docs/03-codebase-summary.md` owns module navigation. `docs/04-code-standards.md` requires parameterized queries, scoped sessions, separate public contracts and no generic repository framework. Use functions plus only necessary resource-owning/mapping/contract classes.

## Scope challenge

Reuse the accepted brainstorm contract. The user selected SQLAlchemy + Alembic explicitly. More than eight implementation files are justified by distinct contracts, ORM mappings, migrations, real-database tests, safety tooling and CI ownership. Mapping/model classes are required for the requested records; do not add service-class hierarchies. Limit the plan to three sequential phases. Reduce unrequested additions, not the issue's acceptance criteria.

## Planning verification boundaries

Only reads and plan scaffolding have run. No application tests, dependency compatibility trials, containers, migrations, schema changes or database writes have run. Current official documentation research informs proposals, not proof that the proposed stack passes checks here. Resolve exact dependency patches/digests in implementation and lock them. Database backup must precede schema/data mutation, including test setup.

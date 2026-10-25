---
phase: 3
title: "CI and maintainer verification"
status: done
priority: P1
effort: 4h
dependencies: [2]
---

# CI and maintainer verification

## Goal and current owners

Make canonical storage checks mandatory in existing Backend CI while retaining credential-free local health/export and documenting only implemented routes. Blocked by phase 2 passing. Existing CI Backend calls `make backend-check` at `.github/workflows/ci.yml:27-28`; API contracts uses `make setup` and drift check at `:69-70`; Smoke runs normal Compose at `:87-93`. Existing `Makefile:5,21-26` owns local checks. Main Compose currently has API/web at `compose.yaml:2,17`; keep those independent of test storage.

## File ownership

This sequential executor modifies only:

- `.github/workflows/ci.yml`: test PostgreSQL service and mandatory database invocation in existing Backend job.
- `Makefile`: validate/tighten phase-1 command dispatch and CI fail-closed behavior.
- `scripts/check-database.sh`: CI service-container adapter and cleanup verification.
- `README.md`: shipped storage scope, DB-free checks and explicit opt-in database checks.
- `docs/03-codebase-summary.md`: implemented module/test/migration navigation.
- `docs/06-deployment-guide.md`: local migration/backup/restore verification route; production deployment remains a requirement.

Do not change generated API files, web code, main Compose, rulesets, or unrelated product docs. No two phases edit shared files simultaneously.

## Tests Before (red)

1. Verify phase-1 guard tests cover CI missing URL/service, identity mismatch and failed backups; extend those existing tests only if the CI adapter adds a meaningful untested branch (then explicitly transfer ownership of `apps/backend/tests/unit/database/test_database_guard.py`).
2. Exercise Backend command with `CI=true` and no test service/config: it must fail, not silently pass by excluding database tests. Exercise database-free command with test URL unset and ensure health/OpenAPI still pass.
3. Compare workflow command ownership against every current caller: `Makefile:5` and `.github/workflows/ci.yml:28` call backend-check; `Makefile:3` and `.github/workflows/ci.yml:69` call setup. Do not alter setup to connect/migrate automatically.
4. Inject failed final backup and failed target verification. Assert nonzero exit, closed sessions/stopped verified owned service, released port, and retained backing data/private archives. Prove clean scenarios receive different fresh targets and committed immutable records do not leak to the next scenario.

## Implementation and Refactor

1. Add PostgreSQL service to Backend only with the same resolved image as local tests, isolated job-scoped test credentials, health check and deterministic port. Follow phase 1's control/empty-install/upgrade/storage/restore target ownership table, with separate fresh databases and backup before each control-target CREATE/DROP and scenario mutation phase. Resolve service identity through actual container ID/server metadata, not a DSN name heuristic. Retain existing job/check name, action SHA pins, timeouts and read-only permissions.
2. Backend `make backend-check` always runs existing checks; in CI it additionally requires the database runner and fails if configuration/service/backups/tests fail. Local `make check` runs explicit DB-free paths, while `make database-check` opts into complete real DB verification. No skip marker turning required DB failures into green CI; explicit directory discovery owns exclusion locally.
3. Reuse phase-1 runner for backup-before-scenario/migration/seed/cleanup. Use service container PostgreSQL client tools for compatible dump/restore versions; do not require unpinned host client tools. Keep archives private/ephemeral; never upload mailbox-like test dumps as artifacts or log credentials.
4. Distinguish process shutdown from destructive cleanup. On successful guards/backups/verification, dispose only owned targets and private disposable files. On failed guard/final backup, return failure, close sessions, stop only previously verified owned local processes, retain backing storage and valid archives, and report the private recovery path without credentials. Never auto-remove the recovery directory/container or volumes on this failure path. CI service containers are job-owned; retention exists only until platform job disposal, with no durable raw-dump artifact or cross-job recovery promise. Do not stop unrelated containers. Check deterministic port ownership before local startup.
5. Update smallest owning docs after reading them. Link Makefile, test manifest, migrations and runner instead of duplicating implementation. Document test/development separation, proposed-to-shipped command transition, backup location/retention, restore check, and limits: no production backup storage/credentials/deployment, provider sync, auth, worker or projection execution.
6. Refactor command dispatch only to remove actual duplication; do not add a generic database orchestration framework.

<!-- Updated: owner-approved red-team corrections — fresh scenario targets and recovery-safe cleanup. -->

## Tests After and verification commands

Existing commands preserved: `make setup`, `make backend-check`, `make check`, `make check-api-drift`, `make up`, `make down`, `npm --prefix apps/web run test:smoke`. Database targets and runner commands below are implemented.

1. Run contract/guard unit tests first, then `make database-up`, `make database-check`, `make database-down`; verify no owned test process/port remains after success or injected failure. Runner must back up before destructive teardown too; if it fails, retain storage/archives while stopping the verified owned service.
2. Test empty-to-head and seeded initial-to-head migration on distinct fresh targets; assert head revision, schema parity, representative data and constraints. Run real restore verification into another guarded target. Include TRUNCATE rejection, deterministic two-session tests, exact selected-text binding and canonical projection eligibility in the complete database suite.
3. With test DB configuration unset, run `make check` and `make check-api-drift`; verify health route and offline exporter do not load required storage configuration. Existing contract test is `apps/backend/tests/contracts/test_openapi.py:23-34`; app composition is `apps/backend/src/email_support/main.py:7-8`.
4. Run `docker compose -f compose.test.yaml config --quiet`, normal Compose config and existing browser smoke if container/runtime dependencies changed; shut down only owned normal/test stacks afterward. No new UI E2E suite is needed for storage-only contracts.
5. Run existing Backend job with its service, and a deliberate missing-service/config negative check locally or in an equivalent isolated harness. Record actual results; GitHub green evidence is pending until workflow execution. Retain required check names; do not modify rulesets in this issue.
6. Verify docs links and commands against final files. Review public docs/logs for secrets, instance infrastructure, dumps and unsupported shipped claims.

## Risk, compatibility and rollback

Medium likelihood / high impact: CI green without DB coverage; CI-required branch plus explicit failure checks prevent it. Medium/medium: client/server dump mismatch or restore failure; same image tools and real restore exercise detect it. Low/high: app startup accidentally requires DB; unset-URL health/export regression checks protect the existing slice.

Runtime/public API contracts remain compatible, with no generated API change expected. Local DB checks are opt-in and explicitly documented; CI is mandatory. Roll back workflow/Makefile/docs changes without deleting schema/data; retain backups before recovery and restore only guarded targets. Normal production restore/deploy remains separately authorized work under `docs/06-deployment-guide.md:17-27`.

## Success and handoff

Execution checklist:

- [x] Prove CI dispatch fails without required database configuration or service.
- [x] Integrate PostgreSQL into Backend CI while preserving database-free checks.
- [x] Verify cleanup success/failure behavior and update owning documentation.
- [x] Run final checks and report acceptance evidence without merging or closing the issue.

Acceptance means actual check evidence for all requested families, both migration paths, rollback, immutable provenance, restore and CI dispatch. Report commands/results and any verification gaps. Do not close Issue #3, move it to Done, merge, release or deploy without explicit owner authorization. Plan completion records never replace evergreen source authority.

Unresolved technical questions: none after the owner-approved corrections. Whole-plan document verification and owner plan acceptance are complete.

## Execution evidence (2026-10-25)

- `make check` passed: 26 backend tests, 14 web tests, Ruff, formatting, strict mypy, TypeScript checks, lint, and production build.
- `make check-api-drift` passed with no generated API changes.
- `make database-check` passed all 30 database tests and removed its owned local container/network; port 55432 was free.
- Backend CI's missing-configuration path was exercised locally and failed closed. The positive CI adapter was exercised against a disposable PostgreSQL container using its exact 64-character container ID; all 30 tests passed. Workflow YAML and pinned image alignment were checked locally.
- Cleanup success and injected backup/identity failures were verified. Failure paths stopped only the verified local service and retained recovery files. Old recovery archives remain in the ignored `.test-database/recovery/` directory; the final successful run removed its own archives.
- GitHub Actions has not run for this branch because no push or pull request was authorized. Issue #3 remains Ready, and no PR was created.

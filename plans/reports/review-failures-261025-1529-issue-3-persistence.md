# Failure mode review: canonical persistence plan

Scope: PLAN ONLY, `--tdd --hard --yagni`. Read all four files in `plans/261025-1529-issue-3-canonical-persistence/`, root AGENTS.md, the requested architecture/standards/manifests/workflow, and the owning codebase/deployment documentation and health/OpenAPI sources. No application changes, tests, builds, lint or type checks ran. No processes were started. Review used the installed ak-scout and ak-code-review protocols with inline targeted scouting.

Assessment: changes needed before execution. No Critical findings; one High and two Medium findings. The proposed rollback and cross-revision preservation tests already address the stated risks and should be retained.

## Findings

### High: Serial-only tests cannot establish the locking and construction-seal guarantees

Plan location: `plans/261025-1529-issue-3-canonical-persistence/phase-01-start.md:58` promises parent locking with `max(version_number)+1` but explicitly chooses serial numbering tests; `:60` makes citation immutability depend on parent locking. `plans/261025-1529-issue-3-canonical-persistence/phase-02-typed-storage-and-invariants.md:79` additionally prohibits parallel tests, while `:40-44` reuses the construction seal for knowledge.

Evidence: `docs/04-code-standards.md:38-42` requires tests at the layer proving the invariant and deterministic synchronization for concurrency tests. The proposed storage modules and migrations do not exist yet, so there is no implementation evidence overriding this gap.

Failure scenario: an implementation accidentally computes the maximum before acquiring the briefing lock. All planned sequential numbering tests pass, but two independent transactions compute the same next number and one valid append fails with a unique violation. Similarly, a citation trigger that checks the seal before waiting for its lock passes every sequential mutation test while leaving the seal/insert interleaving unproved.

Minimal correction: keep suite/scenario scheduling serial, but allow two explicitly coordinated connections inside narrowly scoped tests. Prove two appends to the same briefing both commit with distinct consecutive versions, and prove citation writes cannot cross sealing for both version and knowledge parents. Use events/barriers or observable lock state and bounded timeouts, not sleeps. Exercise both relevant lock orders; do not add worker/job concurrency or a general concurrency framework.

### Medium: UPDATE/DELETE triggers leave a normal SQL path to erase immutable history

Plan location: `plans/261025-1529-issue-3-canonical-persistence/phase-01-start.md:47-60` specifies UPDATE/DELETE rejection for evidence/history and INSERT/UPDATE/DELETE enforcement for citations. `plans/261025-1529-issue-3-canonical-persistence/phase-02-typed-storage-and-invariants.md:37-44` similarly describes append-only decisions and immutable knowledge membership. The aggregate acceptance criterion at `plans/261025-1529-issue-3-canonical-persistence/plan.md:36` promises rejection of ordinary SQL changes to immutable history.

Evidence: `docs/04-code-standards.md:27` requires immutable report-version binding. PostgreSQL documents that TRUNCATE bypasses DELETE triggers and supports separate statement-level TRUNCATE triggers. This does not require disabling existing triggers. See [PostgreSQL 18 TRUNCATE](https://www.postgresql.org/docs/18/sql-truncate.html#SQL-TRUNCATE-NOTES) and [CREATE TRIGGER](https://www.postgresql.org/docs/18/sql-createtrigger.html).

Failure scenario: a connection granted TRUNCATE runs `TRUNCATE briefing_version_evidence` and removes published citations without any parent-row mutation or trigger disabling. This table is a leaf in the first migration; later citation tables have the same issue. The plan specifies no runtime privilege boundary excluding this operation, and all listed raw-SQL UPDATE/DELETE tests still pass.

Minimal correction: add a rejecting BEFORE TRUNCATE statement trigger on each immutable table and prove it with raw SQL, or explicitly establish and test a runtime role without TRUNCATE privileges. A small rejecting trigger matches the existing design without introducing a new role-management subsystem. Fixture cleanup must use a separately guarded database/schema lifecycle rather than bypassing history triggers during ordinary operations.

### Medium: Failed final backup has no cleanup policy satisfying both safety and process ownership

Plan location: `plans/261025-1529-issue-3-canonical-persistence/phase-01-start.md:73` requires successful identity checks/dump/list before cleanup; `:80-86` promises finally/trap disposal and no remaining owned processes. `plans/261025-1529-issue-3-canonical-persistence/phase-03-local-ci-and-verification.md:39` orders temporary-file/service removal after required backups, and `:47` requires no process/port after injected failure.

Evidence: `docs/06-deployment-guide.md:17` requires backing up before schema changes and stopping promotion on failure. The supplied AGENTS.md process rules require stopping owned processes and avoiding orphans. Existing teardown in `Makefile:15-16` only concerns the ordinary stack; there is currently no test runner or test Compose cleanup implementation to resolve the conflict.

Failure scenario: a database test completes, then final pg_dump fails because the server has become unavailable or the archive filesystem is full. A trap that observes the backup gate cannot remove the temporary database/storage, while a trap that always tears down ephemeral storage loses the only unarchived state. Returning early also leaves the owned container/port or temp archives behind, contradicting the injected-failure acceptance check.

Minimal correction: distinguish resource shutdown from destructive data cleanup. On failed backup or failed target verification, return failure, close sessions and stop only the verified owned process/container without removing its backing data or last valid archives. Retain a private recovery location and report it without credentials/content. Delete storage/archives only after the required successful guard/backup/verification. Define how ephemeral test storage survives this failure path; add one injected final-backup failure check for exit status, stopped port, and retained recovery material.

## Verification sample and limits

Sampled 10 claims/contracts per phase, 30 total. This is 30 source/contract comparisons, not 30 successful runtime checks. Proposed behavior was checked for internal consistency and ownership, not represented as shipped behavior.

| Phase | Ten sampled claims/contracts | Result and owning evidence |
| --- | --- | --- |
| 1 | Health-only composition; absent persistence dependencies; storage/models boundary; caller-owned transactions; nullable/UTC contracts; real PostgreSQL requirement; isolated test data; database-free current checks; row-lock numbering/citation sealing; final backed-up cleanup | First eight are consistent with `main.py:5-8`, `pyproject.toml:10-22`, `docs/03-codebase-summary.md:12`, `docs/04-code-standards.md:10-12,26,40-42`, and `Makefile:21-26`. Proposed transaction/DB behavior is not implemented. Last two expose the High concurrency and Medium cleanup gaps above. |
| 2 | Atomic approval/action; exact immutable binding; canonical/projected ownership; raw versus approved evidence; explicit preferences; cross-briefing composite FK; source-version knowledge binding; rollback after partial write; real initial-to-head preservation; separate guarded restore | Architectural claims match `docs/02-system-architecture.md:35,43-53` and `docs/04-code-standards.md:27`. Composite FKs/triggers and operations are proposed contracts only. `phase-02-typed-storage-and-invariants.md:60-61,65,76,79` explicitly covers rollback, historical SQL seeds independent of head mappings, and real restore; no duplicate finding raised. Immutability still has the TRUNCATE/concurrency gaps above. |
| 3 | Backend caller; API-contract caller; smoke caller; current API/web-only Compose; unchanged setup semantics; mandatory CI database dispatch; missing-service negative test; same-image database clients; DB-free health/export regression; cleanup after injected failure | Current callers/shape verified at `.github/workflows/ci.yml:27-28,69-70,87-93`, `compose.yaml:2,17`, `Makefile:3,18-19`, `main.py:7-8`, and `tests/contracts/test_openapi.py:23-34` (last two backend-relative). Mandatory dispatch/service/client use and negative checks are explicitly proposed at `phase-03-local-ci-and-verification.md:30-38,49-51`; no green CI claimed. Final cleanup remains underspecified above. |

Actual tools/actions: local file discovery, numbered reads and Git status; primary PostgreSQL documentation lookup. Existing runnable command owners verified from Makefile/workflow; no commands were executed to validate the application. Proposed tools remain SQLAlchemy/Psycopg/Alembic/pytest-asyncio dependencies, both migration revisions, compose.test.yaml, check-database.sh, database fixtures, and all database Make targets. Image patch/digest, container identity adapter behavior, trigger definitions, fixture lifetimes, catalog checks, dump/restore success and GitHub execution remain implementation-time evidence.

Unresolved questions: none requiring a product decision; resolve the three execution/verification gaps above in the plan.

Status: DONE_WITH_CONCERNS
Summary: Completed the scoped failure-mode review with 30 sampled source/contract comparisons. Found one High verification gap and two Medium safety/integrity gaps.
Concerns/Blockers: deterministic concurrency coverage, TRUNCATE immutability, and failure-safe backed-up cleanup need concrete plan corrections before execution.

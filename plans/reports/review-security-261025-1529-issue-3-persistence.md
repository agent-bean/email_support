# Security adversary: Issue #3 persistence plan

Reviewed all four files in `plans/261025-1529-issue-3-canonical-persistence/` against AGENTS.md, architecture, code standards, backend composition/manifest/tests, Makefile, Compose and CI. Applied the scout and code-review skills. Scope: PLAN ONLY, `--tdd --hard --yagni`, Fact Checker + Contract Verifier tier. No implementation, database mutation, app tests, lint or build ran.

## Finding: High — TRUNCATE bypasses the immutable citation boundary

- Plan location: `plans/261025-1529-issue-3-canonical-persistence/phase-01-start.md:60`; related `phase-02-typed-storage-and-invariants.md:37`, `:40`, `:44` and `plan.md:36`.
- Repository evidence: `docs/04-code-standards.md:27` binds approval to an immutable report version; `docs/02-system-architecture.md:43` makes PostgreSQL authoritative for evidence, versions and approvals. The proposed schema at `phase-01-start.md:50` gives `briefing_version_evidence` outgoing FKs but no incoming FK, and `:60` protects citation INSERT/UPDATE/DELETE through the parent seal. Phase 2's knowledge citation table has the same exposure.
- Engine evidence: PostgreSQL 18 explicitly states that TRUNCATE does not fire DELETE triggers and supports separate TRUNCATE triggers. See [TRUNCATE](https://www.postgresql.org/docs/18/sql-truncate.html) and [CREATE TRIGGER](https://www.postgresql.org/docs/18/sql-createtrigger.html). This is a distinct event; protecting row mutations does not cover it.
- Concrete failure: after creating and sealing a version, an ordinary `TRUNCATE briefing_version_evidence` removes its citation membership without a row trigger, parent seal check or FK violation. `TRUNCATE knowledge_evidence` similarly strips provenance from approved knowledge. The version and approval survive, falsely appearing to retain their immutable provenance. This requires table TRUNCATE privilege, which the plan does not exclude; its single test/migration role has no specified privilege separation. It does not require disabling triggers or altering their definitions.
- Smallest correction: explicitly reject TRUNCATE with a statement-level `BEFORE TRUNCATE` trigger on immutable history/binding/citation tables, reusing the rejection function where appropriate. Add backed-up raw-SQL negative scenarios for both citation tables and representative parent `TRUNCATE ... CASCADE`; after rollback, verify history and links from a fresh session. Keep ordinary privileged DDL/trigger disabling outside the guarantee as already stated. No production role-management subsystem is needed.

## Verification ledger

30 claim/contract samples inspected: 10 per phase. These counts measure source/contract inspection, not runnable implementation proof. Existing claims match the inspected repository. Proposed contracts remain unimplemented; the single finding applies across phases 1 and 2.

| Phase 1 sample | Evidence and result |
| --- | --- |
| Health-only composition | `apps/backend/src/email_support/main.py:7` — existing, verified. |
| Persistence dependencies absent | `apps/backend/pyproject.toml:10` and `:17` — existing, verified. |
| Contract/storage ownership | `docs/03-codebase-summary.md:12` — existing, verified. |
| Real PostgreSQL tests required | `docs/04-code-standards.md:40` — existing contract, verified. |
| Development/test separation | `docs/04-code-standards.md:42`; phase 1 `:71` — proposed isolated stack aligns. |
| Database-free default test invocation | `Makefile:23`; phase 1 `:80` — existing caller verified; directory dispatch proposed. |
| Caller transaction ownership | `docs/04-code-standards.md:26`; phase 1 `:56` — proposed unit of work aligns. |
| Exact target identity before writes | Phase 1 `:65`, `:72` — concrete proposed container/server/database/role checks and negative tests. |
| Backup before mutating scenarios | Phase 1 `:73`; `plan.md:39` — proposed dump/list gating aligns; no backup implementation exists. |
| Immutable version/citation membership | Phase 1 `:47`, `:49`, `:60`; `docs/04-code-standards.md:27` — TRUNCATE gap above. |

| Phase 2 sample | Evidence and result |
| --- | --- |
| Approval/action atomicity | `docs/02-system-architecture.md:35`; phase 2 `:52`, `:60` — proposed helper and rollback evidence align. |
| Exact report/action/recipient binding | `docs/04-code-standards.md:27`; phase 2 `:37`, `:50` — proposed immutable single source of binding aligns. |
| Cross-briefing approval rejection | Phase 1 `:49`; phase 2 `:37` — proposed matching composite unique/FK pair. |
| Duplicate action prevention | Phase 2 `:38`, `:59` — proposed unique approval FK and negative test align. |
| Knowledge approval/version/action binding | Phase 2 `:39`, `:44`, `:59` — proposed composite FK plus action-kind trigger align. |
| Citation subset and preservation | Phase 2 `:40`, `:44`; `docs/02-system-architecture.md:51` — proposed subset check aligns; TRUNCATE gap inherited. |
| Immediate knowledge ineligibility | `docs/02-system-architecture.md:53`; phase 2 `:54` — proposed read filtering aligns. |
| Projection is not approval authority | `docs/02-system-architecture.md:47`; phase 2 `:42`, `:46` — proposed recovery-only metadata aligns. |
| No implicit preference inference | `docs/02-system-architecture.md:53`; phase 2 `:41` — explicit values only, proposed contract aligns. |
| Real cross-revision preservation | Phase 1 `:27`; phase 2 `:24`, `:61`, `:65` — two proposed substantive revisions and initial-valid seed align. |

| Phase 3 sample | Evidence and result |
| --- | --- |
| Backend CI dispatch owner | `.github/workflows/ci.yml:27` and `:28` — existing, verified. |
| API-contract job setup/drift owner | `.github/workflows/ci.yml:69` and `:70` — existing, verified. |
| Smoke owns normal Compose | `.github/workflows/ci.yml:87` through `:93` — existing, verified. |
| Normal Compose has API/web only | `compose.yaml:2` and `:17` — existing, verified. |
| Normal published ports are loopback | `compose.yaml:6` and `:27` — existing, verified. |
| Setup presently installs only | `Makefile:3`, `:18`, `:31` — existing, verified; no migration coupling proposed. |
| CI must not silently skip DB | Phase 3 `:31`, `:37`, `:51`; `.github/workflows/ci.yml:28` — concrete proposed failing negative path aligns. |
| Preserve health/export without storage config | `apps/backend/src/email_support/main.py:7`; `apps/backend/tests/contracts/test_openapi.py:23`; phase 3 `:49` — existing owners verified; regression checks proposed. |
| Read-only workflow permission/check name | `.github/workflows/ci.yml:9`, `:14`; phase 3 `:36` — existing facts verified; preservation explicit. |
| Production restore/deploy remains separate | `docs/06-deployment-guide.md:17` through `:27`; phase 3 `:40`, `:58` — existing requirements distinct from proposed disposable local/CI recovery. |

## Other attack paths and scope boundaries

- Backup/target isolation: exact database, role, owned container and server identity; no app-URL fallback; dump plus archive-list failure before mutations; separately guarded scratch restore; private archive permissions and owned-resource cleanup are explicit plan requirements. No additional material plan defect established. Their implementation and failure cleanup remain unverified.
- Seal enforcement: the plan explicitly covers late citation insertion, modifications/removal, false-to-true-only sealing, deferred rejection of unsealed commits, sealed reads and raw SQL testing. Beyond TRUNCATE, no proven bypass was established from this plan text. The SQL implementation must still be reviewed.
- Malformed SQL bindings: database enforcement of invalid shapes, recipient canonical order/duplicates, exact version ownership, action kind and knowledge citation subset is explicitly planned. No need to add a second approval binding or a speculative authorization layer.
- Logging/data exposure: phase 1 `:73` prohibits DSN/content logs and makes dumps private; phase 3 `:38`, `:52` prohibits dump artifacts and calls for log/doc review. `docs/04-code-standards.md:28` already forbids secret/email/prompt logging. No current storage logger or new API exists to substantiate a leak finding.
- Approval records do not prove human identity or execution authority. Phase 2 `:37`, `:52` makes that limitation explicit and defers execution-time checks. Authentication, delivery, jobs, encryption infrastructure and production backup operations are outside this review's fixed scope.

Unresolved questions: none. Implementation evidence remains pending by design.

Status: DONE_WITH_CONCERNS
Summary: Reviewed 30 sampled claims/contracts across all phases; one High immutability gap needs a small plan correction before implementation.
Concerns/Blockers: Explicit TRUNCATE rejection and negative SQL coverage are missing from the promised immutable history boundary.

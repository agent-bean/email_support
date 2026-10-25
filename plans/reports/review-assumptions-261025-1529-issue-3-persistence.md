# Assumption Destroyer review: Issue #3 persistence plan

Scope: all four files in `plans/261025-1529-issue-3-canonical-persistence/`; plan only, `--tdd --hard --yagni`. Reviewed against live Issue #3, AGENTS.md, architecture, standards, manifests, commands, CI, current health/export code, and the recorded accepted direction. Used code-review and scout protocols inline. No implementation, tests, lint, build, containers, migrations, or external writes ran. All storage paths and database commands in the plan are **proposed**, not available capabilities.

Assessment: correct existing-source references and sensible issue boundaries, but resolve the approval-content binding and define executable database scenario isolation before implementation. Projection freshness also needs a coherent state contract. No Critical findings.

## Findings

### High — Approval binds a version but does not bind the new knowledge content

- **Plan location:** `phase-02-typed-storage-and-invariants.md:39-44`, `:52-54`.
- **Evidence:** `docs/01-project-overview-pdr.md:26-27` defines approval as an exact content-version decision and knowledge as owner-approved facts/summaries; `:35` requires authorization for promotion; `:43-44` allows selected knowledge and invalidates approval after content edits. `docs/04-code-standards.md:27` requires immutable-version binding. The proposed knowledge row accepts independent `content text`; the listed checks establish only action kind, version identity, and evidence membership.
- **Failure scenario:** version V contains an approved factual report. A valid save-knowledge approval for V is supplied to create a knowledge row whose content is a newly generated claim absent from V. All specified FKs, action-kind checks, citation checks and seals pass. The row is immediately eligible although its actual reusable content was never approved. Immutability then preserves the wrong payload. This is an exact-content storage-contract gap, not a request to implement authentication or worker authorization.
- **Smallest correction:** define the save contract now: derive stored text from the approved immutable content or from a precise selection represented by that approval. Reject arbitrary replacement text in the typed storage operation. If independently rewritten summaries are intended, their exact content must be part of the approved immutable payload. Add a negative test using a valid approval/version and changed knowledge text. Do not add an approval framework or executor.

### Medium — Projection version states do not match immutable knowledge semantics

- **Plan location:** `phase-02-typed-storage-and-invariants.md:39-46`, `:67`.
- **Evidence:** `docs/02-system-architecture.md:45,49` requires source/embedding provenance and canonical-version/eligibility checks. The proposed knowledge content and source binding are immutable (`phase-02:39,44`); projection `source_version_id` must equal that immutable binding (`:42`). Only `projected_version_id` has a free-standing version FK; the plan nevertheless calls a differing version “stale” and mentions source changes (`:42,46`).
- **Failure scenario:** K is permanently derived from V1. Creating V2 cannot update K's canonical source, so K never becomes V2 through the allowed operations. A metadata write can instead record an unrelated company's V9 as K's projected version because V9 satisfies the single FK. This produces a nominal stale state that cannot describe a legitimate prior projection of K. Separately, changing embedding implementation cannot be compared against an expected embedding version because only one embedding version is recorded.
- **Smallest correction:** explicitly define the valid states under the immutable-K model: never projected, projected from K's exact canonical version, and invalidated eligibility. Reject unrelated projected versions. State that the stored embedding version describes the recorded projection and that desired embedding-version comparison belongs to the future projection caller. Remove unsupported automatic-staleness/source-change claims; do not invent mutable knowledge revisions, jobs, or another version system.

### Medium — Migration scenarios lack a concrete fresh-target/reset owner

- **Plan location:** `phase-01-start.md:34,73,78-80`; `phase-02-typed-storage-and-invariants.md:60-61,79`; `phase-03-local-ci-and-verification.md:47-48`.
- **Evidence:** current `Makefile:21-26` invokes one pytest process, and `apps/backend/pyproject.toml:27-29` has no database fixture/reset convention. The plan's runner migrates before serial DB checks, while the preservation test must start at the initial revision, commit representative data, then upgrade to head. Immutable version/evidence/citation history cannot be cleaned with ordinary row deletion (`phase-01:47-50,60`). Existing code offers no fixture behavior that can be inherited.
- **Failure scenario:** after the runner upgrades the shared test database to head, the preservation test asks Alembic to upgrade to the initial revision; an upgrade cannot rewind an existing head schema. Alternatively, tests create sealed committed rows for independent-connection durability, and ordinary function-session rollback does not remove those committed rows for the next scenario. Serial execution alone solves neither issue. Implementers must invent schema resets, downgrades, or extra target routing absent from the plan.
- **Smallest correction:** specify an explicit lifecycle in the existing runner/conftest design: separate clean guarded targets (or explicit fresh schema lifecycles) for empty-to-head, initial-to-head, ordinary storage tests, and restore; state who creates, migrates, backs up, and destroys each. State how committed durability tests reset before the next scenario without deleting immutable rows or rewinding an adopted database. Keep one serial runner and existing safety guards. A concise fixture/target ownership table is sufficient.

## Standard verification sample

Counts describe plan-claim review, **not passing implementation checks**. “Verified” means supported by current source or an internally consistent, explicitly proposed contract; “Failed” means a concrete contradiction above; “Unverified” means execution-dependent and honestly pending. Ten sampled claims per phase: **23 verified, 3 failed, 4 unverified**.

| Phase | Sampled claim | Result and evidence |
| --- | --- | --- |
| 1 | Health-only composition | Verified — `apps/backend/src/email_support/main.py:5-8`. |
| 1 | Persistence dependencies absent | Verified — `apps/backend/pyproject.toml:10-22`. |
| 1 | ORM/application contract separation | Verified — `docs/03-codebase-summary.md:12`. |
| 1 | Existing backend pytest caller | Verified — `Makefile:21-26`. |
| 1 | PostgreSQL and isolated test data required | Verified — `docs/04-code-standards.md:40-42`. |
| 1 | Caller owns commit, helpers flush | Verified proposed contract — `phase-01:56`; consistent with `docs/04-code-standards.md:26`. |
| 1 | Account/calendar provider-key namespaces represented | Verified proposed contract — `phase-01:42,45-46`; scope matches live Issue #3. |
| 1 | Scenario reset supports both head and prior-revision tests | Failed — lifecycle finding above. |
| 1 | Seal/deferred-trigger behavior protects all ordinary SQL paths | Unverified — proposed `phase-01:60`; no migration exists or was run. |
| 1 | Exact local/CI server-identity and backup guards work | Unverified — proposed `phase-01:65,71-73`; no runner exists or was run. |
| 2 | Atomic approval/action requirement is real | Verified — `docs/02-system-architecture.md:35`. |
| 2 | Cross-briefing approval FK has a unique target | Verified proposed contract — `phase-01:49`, `phase-02:37`. |
| 2 | Single approval binding avoids duplicated mutable action facts | Verified proposed contract — `phase-02:37-38,52`. |
| 2 | Wrong-kind knowledge approval is rejected by design | Verified proposed contract — `phase-02:39,44`. |
| 2 | Eligible knowledge text is necessarily approved text | Failed — content-binding finding above. |
| 2 | Differing projection versions represent meaningful staleness | Failed — projection finding above. |
| 2 | Explicit JSON null preference differs from absent input | Verified proposed contract — `phase-02:41,58`; `docs/04-code-standards.md:12`. |
| 2 | Raw evidence is distinct from approved knowledge | Verified — `docs/02-system-architecture.md:51`; proposed separate tables. |
| 2 | Executor/jobs/leases remain out of scope | Verified — `phase-02:33,46`; accepted direction `plans/reports/brainstorm-261025-1529-issue-3-canonical-persistence.md:17-19`. |
| 2 | Additive upgrade preserves all initial rows and triggers | Unverified — requires proposed migration/catalog/behavior execution. |
| 3 | Backend check name and current caller retained | Verified — `.github/workflows/ci.yml:13-28`. |
| 3 | Setup is currently database-free | Verified — `Makefile:3,18-19,31-32`. |
| 3 | API drift job calls setup and drift command | Verified — `.github/workflows/ci.yml:69-70`. |
| 3 | Normal Compose has API/web only | Verified — `compose.yaml:2,17`. |
| 3 | Smoke uses normal Compose and unconditional teardown | Verified — `.github/workflows/ci.yml:87-93`. |
| 3 | CI uses pinned actions and read-only permissions | Verified — `.github/workflows/ci.yml:9-10,18-22`. |
| 3 | Offline exporter contract path/line exists | Verified — `apps/backend/tests/contracts/test_openapi.py:23-34`. |
| 3 | Production backup/deploy remains separate authorization | Verified — `AGENTS.md:7`; `docs/06-deployment-guide.md:17-27`. |
| 3 | Planned CI-only DB branch need not affect API drift/setup | Verified proposed dispatch — `phase-03:31-38`; setup does not call backend-check today. |
| 3 | Container identity, compatible dump clients and failure cleanup work in Actions | Unverified — proposed service/adapter not implemented or exercised. |

## Boundaries and non-findings

- SQLAlchemy/Alembic and backup-before-change are recorded owner constraints; their existence is not scope creep. No recommendation reverses them.
- Two substantive migrations are justified by the explicit upgrade-preservation criterion; no fake revision is requested.
- Future executor validity, authentication, external delivery, projection execution, job/outbox behavior, and production deployment remain excluded. This report does not require them.
- Existing Make/CI/source references inspected were accurate. New targets, database tests and migration files are consistently labelled proposed.
- No plan status or implementation file was changed. Only this report was authored.

Unresolved questions: whether knowledge-save means exact report text/precise selections or separately reviewed rewritten summaries must be resolved in the contract; the smallest existing-scope option is deriving from the approved immutable content. Target/fixture isolation and valid projection states can be settled by the planner without new product features.

Status: DONE_WITH_CONCERNS
Summary: Three concrete plan corrections identified; source references and issue boundaries otherwise checked using 30 sampled claims.
Concerns/Blockers: Resolve approved knowledge payload binding and deterministic migration/test target lifecycle before implementation; clarify projection metadata version semantics.

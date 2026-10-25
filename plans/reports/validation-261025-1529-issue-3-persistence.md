# Issue #3 planning review and validation

Status: all six red-team corrections approved by the owner and applied. Owner accepted the corrected plan on 2026-10-25; implementation has not begun. Flags: `--tdd --hard --yagni`.

## Evidence and scope

Read all four files under `plans/261025-1529-issue-3-canonical-persistence/`, the accepted brainstorm, current source/manifests/commands, and three independent review reports. Existing app behavior remains the credential-free health slice. SQLAlchemy + Alembic was explicitly selected by the owner. No application tests, builds, dependency trials, containers or database mutations ran during planning.

Reports: [Security](review-security-261025-1529-issue-3-persistence.md), [Assumptions](review-assumptions-261025-1529-issue-3-persistence.md), [Failures](review-failures-261025-1529-issue-3-persistence.md). Seven reviewer findings deduplicate to six, with TRUNCATE counted once at the higher severity: three High, three Medium. All six cite repository/plan lines and pass the evidence filter. The owner approved all six; disposition is Accept for every row below. Original reviews describe the pre-correction draft and remain historical evidence.

## Approved corrections — all applied

| Finding | Severity | Applied delta | Affected phases |
| --- | --- | --- | --- |
| TRUNCATE bypasses row triggers | High | Add rejecting BEFORE TRUNCATE statement triggers on immutable history/binding/citation tables, with backed-up direct-SQL tests for leaf tables and representative CASCADE. Privileged DDL/trigger disabling stays outside the guarantee. | 1, 2 |
| Serial numbering tests do not prove locks | High | Keep the suite serial; add bounded, explicitly coordinated two-session tests for duplicate provider insertion, concurrent version appends and citation/seal races. Use events/barriers or observable lock state, never sleeps or pytest worker parallelism. Deferred seal enforcement must inspect final row state at commit, not the original INSERT event's unsealed snapshot. | 1, 2 |
| Knowledge content is not bound to the approval | High | Store the exact selected knowledge text entries as an immutable, typed snapshot on save-knowledge approvals; send approvals have no knowledge selection. Each knowledge row references one selected entry and derives its text from that snapshot, rather than accepting replacement text. Add selection bounds/shape validation, reject mismatches, and preserve the existing version/evidence provenance constraints. No owner authentication, promotion workflow, API or replay service is added. | 2 |
| Projection freshness conflicts with immutable knowledge | Medium | Define metadata as never projected, projected from this knowledge's exact canonical version, or canonically invalidated. Reject unrelated projected versions. Stored embedding version describes the recorded projection; future projection callers compare their desired embedding version. Remove unsupported automatic source-change/staleness claims; add no new version system. | 2 |
| Fresh-target/reset ownership is unspecified | Medium | Define named guarded scenario targets for empty-to-head, initial-to-head, storage and restore. Runner creates a fresh disposable database per scenario, backs up before setup/migration/seed/cleanup, and never rewinds a head database. Committed reconnect tests finish by disposing their owned target rather than deleting immutable rows. Runner/conftest ownership and administrative control-target backup must be explicit. | 1, 2, 3 |
| Failed cleanup backups conflict with teardown | Medium | Separate stopping owned resources from deleting data. If target verification or final backup fails, fail the run, close sessions, stop only already verified owned processes, and retain backing data and valid private archives. Report a recovery path without credentials. Delete storage only after successful guards/backups; test injected failure, released port and retained recovery material. | 1, 3 |

The knowledge snapshot preserves the single canonical approval binding and supports multiple selected entries without a new approval service. Phase 2 now specifies immutable `approvals.selected_knowledge` as a typed JSON array of exact text entries; `knowledge.selection_index` addresses one entry, with a unique approval/index pair and database action/bounds checks. There is no independently writable knowledge-content column; typed reads derive content from the snapshot. This storage-contract completion is now owner-approved. Issue #10 still owns authorized promotion and replay; Issue #14 owns selection/review UI and stale submissions. Both live issue bodies were checked during initial adjudication.

## Verification results

Standard-tier reviewers each sampled ten claims per phase (30 per reviewer). These are overlapping source/contract inspections, not 90 distinct passing runtime checks. Assumption review reported 23 supported, three failed design claims and four implementation-dependent unknowns; security/failure reviews confirmed the existing source ownership and flagged the gaps above. Do not treat proposed files or external documentation as working implementation evidence.

Controller checks completed before correction application:

- `ak plan validate plans/261025-1529-issue-3-canonical-persistence --json`: valid.
- `ak plan parse ... --json`: three phases, all pending/todo.
- Relative Markdown links in the draft: seven checked, all resolve.
- All three phases contain Tests Before, Refactor and Tests After sections.
- `git diff --check`: passed for tracked changes; new Markdown was also read directly. No application checks ran.
- Live task tool discovery found no applicable session task-management API. Phase checklists and the AgentKit plan index own tracking; do not create extra GitHub issues or Codex chats.

## Validation session 1 — 2026-10-25

Trigger: mandatory hard-mode red-team gate. One material question was asked; settled SQLAlchemy/Alembic and scope decisions were not reopened.

**Exact question:** The Issue #3 draft has six proposed corrections: block TRUNCATE on immutable history; add deterministic two-session tests; bind saved knowledge to exact text captured on its approval; define valid projection states; use fresh guarded database targets per scenario; and retain recovery data if cleanup backups fail. Apply all six to the plan?

**Options:** Apply all six (Recommended) | Review each correction first | Revise the proposed corrections.

**Answer:** Apply all six (Recommended).

Rationale: complete the existing persistence integrity/recovery contract, including the exact knowledge payload, without adding later authorization, worker or projection execution features. The answer approves correction application, not final plan acceptance or implementation.

Propagation: phases 1/2 cover TRUNCATE and coordinated sessions; phase 2 defines exact selected text and valid projection states; phases 1/2/3 share fresh target ownership; phases 1/3 explicitly distinguish process shutdown from destructive cleanup, with phase 2 restore using the same policy. All implementation checklist items remain pending.

### Whole-plan consistency sweep

All four plan files reread after applying six approved decision deltas. Removed serial-only lock verification and the ban on coordinated sessions; removed arbitrary knowledge text and inconsistent content-column claims; removed differing-projection-version staleness and automatic source-change claims; reconciled head versus historical migration target ownership; replaced unconditional deletion with retained recovery data on failed guards/backups. Schema tables, operations, test matrices, command ownership, risks, success criteria and index agree. CI retention is explicitly job-lifetime only; no durable raw-dump artifact is promised. No unresolved design contradiction remains. Runtime compatibility and behavior still require implementation evidence.

Final document verification completed:

- `ak plan validate ... --json`: valid, no format errors.
- `ak plan parse ... --json`: three phases, 12 tasks, zero complete; pending/todo states retained.
- `ak plan reindex --apply --json` and `ak plan use ... --json`: corrected files indexed and active plan pinned.
- Read all four final plan files; all eight relative Markdown links resolve, index is 66 lines, every phase has Tests Before/Refactor/Tests After, and no trailing whitespace was found.
- Targeted stale-claim checks: zero occurrences of the superseded serial-only test, arbitrary content-column, unrelated-version staleness or pending-correction approval claims in executable plan files.
- Six approved deltas reconciled; zero unresolved document contradictions. Original review reports intentionally remain historical.
- `git diff --check`: passed. New plan files were explicitly checked by the document script because they are untracked.
- No application tests, builds, dependency trials, containers, schema or data changes ran. Stack compatibility, trigger behavior, exact image/dependency patches and actual hosted CI remain implementation-time verification gates.

## Validation session 2 — 2026-10-25

Owner requested “chuyển path sang relative” and accepted the corrected plan with “tôi thấy plan này ổn rồi”. Converted file inventories and the cook handoff to repository-relative paths; existing document-relative Markdown links remain valid. Plan acceptance is complete. Execution status remains pending because implementation has not begun.

Final session checks: `ak plan validate` passed; parsing confirms three phases, 12 tasks and zero complete. All relative Markdown links resolve, all phases retain TDD sections, no absolute home paths or trailing whitespace remain in the plan and validation report, and `git diff --check` passed. No application checks or database mutations ran.

## Cook readiness

No unresolved design question remains. Ready for cook when requested. Handoff: `/ak:cook plans/261025-1529-issue-3-canonical-persistence/plan.md --tdd --yagni`.

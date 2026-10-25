# Issue #2 plan validation and review disposition

Scope: `--yagni --hard --tdd`, planning only on `docs/issue-2-foundation-plan`. The [plan index](../261024-1819-issue-2-typed-foundation/plan.md) and its three phases are execution authority; this report records validation history. No implementation, commit, push, merge, issue closure or deployment is authorized by this record.

## Session 1 — 2026-10-24

**Trigger:** Three independent reviewers identified test discovery, drift fault-injection and cancellation coverage defects. **Questions asked:** 1, grouping three bounded corrections within accepted scope.

### Question and answer

Exact question:

> Phản biện plan tìm thấy 3 điểm mức Medium. Tôi đề xuất: (1) giới hạn Vitest vào tests dưới src để không chạy nhầm Playwright; (2) kiểm tra generated files chưa commit trước khi regenerate, rồi kiểm tra drift sau đó, kèm test contract cũ; (3) thêm test hủy request từ TanStack Query và kết hợp signal hủy với timeout. Bạn muốn xử lý thế nào?

Options: `Áp dụng cả ba (đề xuất)` | `Xem từng phát hiện trước` | `Giữ nguyên plan`.

**Answer:** `Áp dụng cả ba (đề xuất)`.

The question's original severity wording was corrected in commentary before the answer: test discovery is High; drift probes and cancellation coverage are Medium. The proposed corrections did not change. The owner's explicit answer arrived after context recovery and confirms application of all three. No further product/architecture choice is inferred.

### Review disposition

| Severity / finding | Evidence | Applied resolution | Controller recheck |
| --- | --- | --- | --- |
| High: Vitest can collect Playwright's default-matching spec. | [Assumptions review, finding 1](review-assumptions-261024-1827-issue-2-foundation.md). | Phase 2 owns src-only Vitest include `src/**/*.test.{ts,tsx}`; phase 3 owns explicit Playwright `testDir` and smoke match. Unfiltered unit run needs no services/browser; smoke `--list` proves separate collection after the spec exists. | Requirements, file ownership, commands, matrix and exit checklist agree. Actual tool discovery remains an implementation check. |
| Medium: regeneration can erase dirty-output fault probes before status sees them. | [Assumptions review, finding 2](review-assumptions-261024-1827-issue-2-foundation.md), [failure review, finding 1](review-failures-261024-1827-issue-2-foundation.md), [security review](review-security-261024-1827-issue-2-foundation.md). | Scoped dirty-artifact preflight refuses before generation without overwriting evidence; scoped postflight follows export/generation. Dirty staged/unstaged/deleted/untracked probes are separate from clean committed stale-output/source-contract probes. Explicit generation remains the writer; no unrelated clean-tree requirement/index mutation. | Phase 3 sequence, negative oracles, commands, matrix and risk are consistent; index reflects both gates. Actual script execution is future work. |
| Medium: caller cancellation has no tests-before case or signal composition contract. | [Failure review, finding 2](review-failures-261024-1827-issue-2-foundation.md). | Phase 2 passes Query signal through helper/generated SDK to Fetch, composes a deadline, tests caller/already-aborted signals separately from timeout, preserves cancellation and cleans manual timers/listeners. No cancel UI added. | Architecture, inventory, tests-before, green steps, matrix, risks and exit criteria agree. Actual generated client behavior remains unverified. |

Original reports are immutable assessments of the earlier draft; their old line references and unresolved wording are historical. This disposition records the owner's accepted corrections without claiming a second independent review or runtime proof.

### Confirmed decisions and completed planning actions

- [x] Isolate unit/browser discovery in phases 2/3 and propagate the check to the plan index.
- [x] Separate dirty-artifact guards from committed CI drift proof throughout phase 3 and the index.
- [x] Add caller/deadline cancellation behavior and meaningful tests-before to phase 2 and index.

These checked items are plan edits only. Every implementation item in the plan and phase exit checklists remains unchecked.

## Verification Results

**Tier:** Standard, Fact Checker + Contract Verifier, 10 claims per phase. [Original 30-claim table](review-assumptions-261024-1827-issue-2-foundation.md) assessed 23 VERIFIED / 2 FAILED / 5 UNVERIFIED. After owner-approved corrections, controller rechecked claims 2.10 (suite discovery) and 3.5 (drift probes): both now have consistent, executable proposed contracts. Current plan assessment: **25 VERIFIED / 0 FAILED / 5 UNVERIFIED**. The additional cancellation finding is also resolved at the plan-contract level.

VERIFIED means source-backed requirement or internally consistent proposal, not implemented behavior. No application files or checks exist at the documentation-only baseline. The five unresolved execution claims are deliberately gated:

1. Phase 1: exact Python/uv/backend dependency compatibility.
2. Phase 1: actual offline exporter byte stability and snapshot alignment.
3. Phase 2: exact Node/Hey API/Zod/TS dependency compatibility and generated compilation.
4. Phase 2: actual generated SDK validation/error/deadline/caller-cancellation behavior.
5. Phase 3: clean installs, local/browser/Compose behavior, hosted checks, live required-check application and separately authorized post-merge evidence.

## Whole-Plan Consistency Sweep

- Inputs reread: index and all three phase files, with accepted decision deltas above.
- Deltas checked: 3; updates cover overview/architecture, file ownership, tests-before, implementation, verification commands, matrices, risk, exit criteria and validation history.
- No API/model/schema or architecture decision changed; no storage/auth/provider/worker/production feature added.
- No contradictory current-plan instruction remains. Superseded research/review suggestions are advisory or historical and linked to controller decisions.
- Application commands remain explicitly planned. Dependency patches, generated inventory and emitted GitHub check names remain implementation discoveries.
- All phases pending with sequential dependencies 1 → 2 → 3 and a single executor; root/generated ownership does not overlap concurrently.

## Tracking and limits

### Document checks actually run

- `ak plan validate <absolute-plan-directory> --json`: valid, no errors.
- `ak plan reindex --apply --json`: recognized all 3 pending phases; 11 phase checklist items remain unchecked.
- Local Markdown link/whitespace sweep: 12 files, 60 local links, zero missing targets or trailing whitespace after repairing four research-report ruleset links and one whitespace line. The checker covers untracked files as well as tracked content.
- `git diff --check`: passed; reported separately because untracked plan files are outside its diff coverage.
- `ak journal validate 2026-10-24-issue-2-foundation-plan-validated`: passed. AgentWiki publish skipped.
- Live GitHub recovery reads: issue #2 OPEN, blocker #1 CLOSED, PR #22 MERGED at baseline SHA; branch remains `docs/issue-2-foundation-plan`. Only local `plans/` Markdown files are untracked.

Live tool discovery exposed no general project task CRUD surface. Durable unchecked plan items are the fallback; CLI active-plan indexing mirrors the three phases. Do not create goals, chats or GitHub issues to imitate task hydration.

No project dev server, watcher, build daemon, container or test runner was started. Process reconciliation found only the existing Playwright MCP service, which is not a task-started application process and was left running. No resource cleanup was needed.

Ready for separately selected implementation after document validation. Final acceptance, closure, merge, deployment and release remain owner-controlled. Neither planning validation nor passing PR checks establishes post-merge/runtime acceptance.

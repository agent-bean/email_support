# Issue #2 plan review: failure modes and contract verification

Scope: plan only; `--yagni --hard --tdd`. Read the three phases, plan index, controller scout, AGENTS, README, architecture, code standards, deployment direction and main ruleset. Reused scout evidence before review. No implementation, installs, tests, builds, browser runs, branches or API mutations performed.

## Assessment

No Critical or High finding verified. Two Medium plan gaps need correction or explicit disposition before execution. Application files and commands are correctly marked proposed; their absence at the documentation-only baseline is not a defect.

## Medium findings

### 1. Regeneration can erase the drift fault before the proposed probe observes it

- Plan: `plans/261024-1819-issue-2-typed-foundation/phase-03-local-runtime-ci-and-handoff.md:52` requires a failure for a modified output and a deleted tracked output. Line 59 specifies exporter, generator, then scoped Git-status rejection; line 96 requires all probes to fail.
- Repository evidence: `docs/04-code-standards.md:43` requires generated OpenAPI drift CI; `docs/04-code-standards.md:53` requires generated contracts aligned with source. `plans/reports/scout-261024-1827-issue-2-foundation.md:56` records the accepted path-limited Git-status approach.
- Failure scenario: in a clean disposable checkout, edit a tracked generated SDK file or delete one. Regeneration restores the committed bytes/file. The post-generation status is clean, so the described script exits successfully despite the explicitly required failing probe. Newly untracked output can likewise disappear if generation cleans its output directory. This is a contradiction between the fault-injection procedure and the specified gate, not evidence that regenerate-and-diff CI is inherently wrong.
- Minimal fix: specify a scoped dirty-artifact precheck before regeneration, followed by the existing post-generation check. Keep the three existing worktree fault probes for the precheck. Separately prove stale committed artifacts fail the post-generation check by committing an altered/deleted fixture in the disposable checkout, or changing the source contract without regenerating outputs. Do not use only dirty-worktree rejection as proof that clean-checkout CI catches stale committed generation.

### 2. Cancellation preservation has no tests-before acceptance case

- Plan: `plans/261024-1819-issue-2-typed-foundation/phase-02-generated-web-contract.md:63` requires preserved abort cancellation. Lines 57–58 and 88–90 enumerate HTTP, JSON, network, timeout and UI tests, but no caller/Query cancellation case. Line 24 defines a separate bounded abort timeout without defining how it combines with caller cancellation.
- Repository evidence: `docs/04-code-standards.md:26` says not to swallow cancellation; lines 38 and 52 require behavior tests at the smallest layer proving the invariant. `docs/02-system-architecture.md:25` assigns server state to TanStack Query.
- Failure scenario: the thin helper creates its own timeout signal and ignores the Query signal. All listed tests pass, including timeout, while cancelling the query leaves its request running until the timeout or response. Alternatively, a broad error conversion hides the caller abort as an ordinary network error. The explicit cancellation requirement is unverified.
- Minimal fix: add one tests-before case passing a caller abort signal through the actual generated SDK boundary, assert the underlying Fetch receives cancellation and settles promptly, and retain the existing independent timeout case. State that the thin helper composes caller cancellation with its deadline and cleans up any manually created timer/listener. No additional framework or user-facing cancellation feature is needed.

## Verified non-findings

- Actual integration is expressly browser → Vite → actual API, without success interception (`phase-03-local-runtime-ci-and-handoff.md:20–24,98`); unit Fetch doubles are scoped to boundary testing (`phase-02-generated-web-contract.md:57–58`).
- Locked installation, strict generated compilation and validation wiring have explicit implementation gates (`phase-01-start.md:50,69–74`; `phase-02-generated-web-contract.md:56–65`). Compatibility is not falsely claimed as established.
- API-unavailable integration and bounded readiness/cleanup are explicitly required (`phase-03-local-runtime-ci-and-handoff.md:22,51,57,60,99`). No extra storage/auth/production infrastructure is justified.
- Required checks run on the implementation PR before activation; final-head runs, live ruleset comparison, owner authorization and post-merge evidence are separate gates (`phase-03-local-runtime-ci-and-handoff.md:65–69`). This matches `docs/04-code-standards.md:43,59`, `.github/rulesets/main.json:5,12–27` and `AGENTS.md:7`.
- Phase sequencing is sequential and tests-before is meaningful for application behavior; initial SDK generation is necessary to make generated imports available, not itself a violation of tests-before wrapper/UI implementation.

## Recommended disposition

Clarify the drift fault-injection algorithm and add cancellation to the existing test matrix. Keep the accepted three-phase scope and architecture. All phase tasks remain pending; no runtime or hosted CI result is established by this review.

## Unresolved questions

None requiring owner product or architecture decisions.

Status: DONE_WITH_CONCERNS
Summary: Verified one drift-probe contradiction and one cancellation verification gap. No Critical or High issue was established; no implementation or plan edits were made.

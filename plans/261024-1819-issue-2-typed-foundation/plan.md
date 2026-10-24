---
title: "Issue #2: Typed API and web foundation"
description: "Establish a real credential-free health slice with generated validated web contracts, local Compose and protected CI."
status: done
priority: P1
effort: 14h
issue: 2
branch: docs/issue-2-foundation-plan
tags: [feature, backend, frontend, api, infra]
blockedBy: []
blocks: []
created: 2026-10-24
---

# Issue #2: Typed API and web foundation

## Overview

Execute only the owner-selected [issue #2](https://github.com/agent-bean/email_support/issues/2), applying `--yagni`. The plan was originally prepared with `--yagni --hard --tdd`, but the implementation request explicitly passed only `--yagni`; the formal `--tdd` mode was not activated. The phase plans supplied tests-before gates, but strict test-first ordering is not evidenced for every change. Session 4 applies a baseline-first, behavior-preserving refactor to group tests by type.

## Agreed outcome and constraints

Real FastAPI `GET /api/health` serves a single Pydantic response/StrEnum. Offline committed OpenAPI generates Hey API Fetch SDK/types/Zod; generated SDK response validation is mandatory. React/Vite uses that client through minimal TanStack Query server state, with bounded errors and accessible textual states.

Use pinned Python 3.13/uv and Node 24 LTS/npm; lock tested exact patches during implementation. Require strict Python/TS, lint, formatting, tests/build, deterministic generation and read-only PR/main CI. Same-origin browser `/api` proxy; fixed loopback API 8000/web 5173; local Compose has API/web only.

Non-goals: worker, storage, OIDC, providers, LLM credentials, deployments, domain/tool/action placeholders, new product decisions and speculative abstractions. More than eight files are justified by required manifests/configuration/tests/generated artifacts; no dummy scaffold. Rough effort is 14 hours, not a deadline.

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Typed backend and offline contract](./phase-01-start.md) | Done |
| 2 | [Generated and validated web contract](./phase-02-generated-web-contract.md) | Done |
| 3 | [Local runtime, CI and handoff](./phase-03-local-runtime-ci-and-handoff.md) | Done |

## Dependencies and ownership

Phase 1 precedes phase 2; phases 1/2 precede phase 3. One executor owns all changes sequentially, including root wrappers; inventories and handoff gates live in phases. Exact dependency compatibility is an early implementation gate, not established evidence. No migration of existing users/data is needed at the documentation-only baseline.

## Success Criteria

- [x] API/export work without LLM credentials, database or running external service.
- [x] Actual generated SDK rejects malformed responses, preserves caller cancellation and enforces its deadline; app TypeScript compiles with all strict flags, and generated TypeScript compiles separately with all strict options except `exactOptionalPropertyTypes`.
- [x] Clean locked installs, focused tests, formatting/lint/type checks and web build pass.
- [x] Unit/browser discovery is isolated; repeat generations are stable; scoped dirty-output preflight and committed-stale postflight probes fail as intended.
- [x] Actual browser reaches actual API through local Compose, and bounded failure is visible.
- [x] Final-head PR checks pass; exact emitted checks protect main before authorized merge, preserving baseline/review separation.
- [x] Commands/docs and evidence distinguish local, hosted PR and post-merge runs; owner explicitly controls final acceptance, closure, merge, deployment and release.

## Evidence and gates

Read [controller scout and accepted corrections](../reports/scout-261024-1827-issue-2-foundation.md), [web research](../reports/researcher-261024-1819-web-contract-toolchain.md), and [backend/CI research](../reports/researcher-261024-1820-backend-ci-toolchain.md). Research recommendations superseded by accepted phase decisions are advisory only. Baseline: `5f81f43622d36cf574246a4b7d3a57c190a0542b`; [README, line 7](../../README.md) records no application commands. All phase commands are proposed until implemented and executed.

## Red Team Review

Three reviewers found 3 distinct findings: 1 High (test discovery) and 2 Medium (drift probes, cancellation coverage). Owner approved all three; phase 2/3 corrections are applied. Original review reports remain historical evidence; [controller disposition](../reports/validation-261024-1827-issue-2-foundation.md) records resolutions and remaining runtime gates.

## Validation Log

Session 1, 2026-10-24: 1 question, all 3 corrections approved. Standard verification sampled 30 claims: initial 23 verified / 2 failed / 5 unverified; controller recheck after corrections: 25 verified / 0 failed / 5 explicitly future runtime gates. See [full question, answer and evidence](../reports/validation-261024-1827-issue-2-foundation.md). These counts assess plan requirements, not working software.

Session 2, 2026-10-24: the owner chose to retain the Hey API SDK and compile generated files through a separate strict TypeScript config with `exactOptionalPropertyTypes` disabled only for that generated project. The app project retains the flag.

### Whole-Plan Consistency Sweep

All four plan files reread; 3 original decision deltas propagated across architecture, inventories, tests, commands, risks and success criteria. All three phases are complete through the reviewed, green PR handoff. The implementation is not merged; no post-merge run, issue closure or whole-issue owner acceptance is claimed. Those decisions remain with the owner.

Session 3, 2026-10-24: final ruleset commit `c3a0f9a` was authored by `javis-27`, pushed, and verified on PR #23 at head `c3a0f9a7e892b881ab60753fb262823b458ef105`. Final-head CI run [40097326072](https://github.com/agent-bean/email_support/actions/runs/40097326072) passed `Backend`, `Web`, `API contracts`, and `Smoke`, each emitted by GitHub Actions app `15368`. Active repository main ruleset `25777101` now requires those exact contexts strictly, with no bypass actors; the existing deletion, non-fast-forward, linear-history and pull-request protections remain. Review policy remains separate; `biendo27` approved the final PR head with no findings. PR #23 remains open for owner acceptance and merge. No post-merge CI was run.

Session 4, 2026-10-24: the existing suites passed before test relocation. Tests are now grouped by type, and the focused suites plus `make check`, `make check-api-drift`, Compose config validation, and hosted checks passed. The first post-move collection found a missing `pytest` fixture import, which was restored before the green rerun. The initial invocation did not activate formal `--tdd`; strict red-green ordering across earlier phases cannot be claimed. The follow-up refactor used the prior green suite as its behavior-preservation baseline. Commit `0dd9b3b` is pushed to PR #23; final-head run [40100660560](https://github.com/agent-bean/email_support/actions/runs/40100660560) passed all four checks, and `biendo27` approved the final head with no findings. PR #23 remains open for owner acceptance and merge.

Session 5, 2026-10-24: code review found that the generated Zod object accepted and stripped fields forbidden by OpenAPI. A regression test reproduced the issue with `{ "status": "ok", "extra": true }`; it passed through as a health response before the fix. `fetchHealth` now overrides the generated validator with a strict schema derived from the generated response shape. The test failed before the fix and passed after it; `make web-check` (14 tests, typecheck, lint, formatting, build) and `make check-api-drift` pass. Commit `b18efd8` is pushed to PR #23 as `javis-27`; `biendo27` approved the updated diff. Hosted run [40101629005](https://github.com/agent-bean/email_support/actions/runs/40101629005) passed all four checks, including the real-browser smoke.

## Unresolved questions

No accepted product decision remains open. Tested package versions, actual generated-file inventory and GitHub-emitted check names are implementation discoveries with explicit gates in phases 1–3.

<!-- slug: issue-2-typed-foundation -->

# Assumption Destroyer review: issue #2 foundation plan

Review-only; flags `--yagni --hard --tdd`. Roles: Fact Checker + Contract Verifier. Work context: repository root. Reviewed all four plan files and the requested repository/scout sources against HEAD `5f81f43622d36cf574246a4b7d3a57c190a0542b`. No application installation, generation, tests, lint, builds, containers, or hosted CI were run. No plan files changed.

Applied the installed `ak-scout` and `ak-code-review` protocols. Scout evidence was read before review; additional local scouting confirmed the documentation-only baseline. A narrow memory registry lookup had no relevant hits and supplied no conclusions. Runtime tool discovery exposed agent dispatchers, but no usable live team-task claiming surface.

## Assessment

Two actionable plan defects: unit/E2E discovery is unspecified across the phase boundary, and the prescribed drift probes conflict with the regeneration order. No Critical finding. Accepted Hey API + Zod, Node 24/Python 3.13 selection, generated strict compilation, minimal Query ownership, and API/web-only scope are preserved. Exact compatibility remains an explicitly deferred implementation experiment, not an unsupported claim of correctness.

## Findings

### High — isolate Vitest and Playwright collection before adding the smoke spec

- Plan locations: `phase-02-generated-web-contract.md:39` defines Vitest jsdom configuration; `phase-03-local-runtime-ci-and-handoff.md:36` adds `apps/web/tests/health-smoke.spec.ts`; `phase-03-local-runtime-ci-and-handoff.md:58` makes the full unit suite part of `check`. Phase 3's inventory at lines 28–45 does not assign a modification to `vite.config.ts` for discovery isolation.
- Supporting repository contract: `docs/04-code-standards.md:38` requires tests at the smallest meaningful layer and `docs/04-code-standards.md:43` requires working CI tests. `plans/reports/scout-261024-1827-issue-2-foundation.md:57` separates controlled boundary tests from real-browser evidence.
- Verified tool behavior: Vitest's [include documentation](https://vitest.dev/config/include) specifies a default pattern matching both `*.test.ts` and `*.spec.ts`; its [exclude documentation](https://vitest.dev/config/exclude) does not exclude this planned `tests/` directory by default. These were read during this review; no package was installed.
- Failing scenario: implement phase 2 with its requested jsdom settings and ordinary unfiltered non-watch Vitest command. Phase 2's explicitly file-filtered test invocation passes. Add the phase 3 Playwright spec and run `make check`/Web CI: Vitest collects that Playwright test as well, loading a second test framework under the wrong runner rather than proving browser behavior. The problem appears only after phase integration.
- Minimal fix: explicitly restrict Vitest discovery to `src/**/*.test.{ts,tsx}` (or explicitly exclude the Playwright directory), and configure Playwright `testDir: './tests'` with its smoke match. Assign this configuration to phase 2 or add the phase 3 modification to the file inventory. Verify the unfiltered unit command passes without browsers/services and `test:smoke` discovers only browser tests.

### Medium — drift mutation probes are erased by the gate they are meant to test

- Plan locations: `phase-03-local-runtime-ci-and-handoff.md:52` requires failure for modified/deleted/new generated files; `phase-03-local-runtime-ci-and-handoff.md:59` prescribes exporter → generator → scoped Git status; line 96 repeats that all drift forms must fail.
- Supporting repository/source contract: `docs/04-code-standards.md:43` requires generated OpenAPI drift checking; `plans/reports/researcher-261024-1819-web-contract-toolchain.md:40` defines the gate as detecting changes produced by regeneration; that report's line 52 requires committed output aligned with source. `plans/reports/scout-261024-1827-issue-2-foundation.md:56` also requires tracked and untracked detection.
- Failing scenario: start with committed correct generated output in the disposable checkout, change a generated file's bytes or delete it, then invoke the prescribed gate. Deterministic regeneration restores the tracked bytes/file before status runs. Status is clean and the command succeeds, contradicting the planned assertion that these probes fail. An arbitrary untracked generated file can likewise disappear if the generator cleans its output directory. This is a test-design contradiction, not evidence that regenerate-then-status is itself unsuitable for CI.
- Minimal fix: define the probes as stale *committed baselines*. In the disposable checkout, commit an altered generated file for the modified case and commit its deletion for the new/untracked case; normal regeneration must then produce `M` and `??` respectively. To test a `D` result, commit an extra obsolete generated file and ensure the generator actually removes obsolete output, or use a controlled gate-level command fixture that removes an artifact after generation. Inspect status immediately before the final assertion and restore the disposable checkout between cases. Alternatively, explicitly require a pre-generation dirty-output guard, but do not silently change the intended CI drift semantics merely to satisfy the probes.

## Checked claims — phase 1 (10)

Status meanings: **VERIFIED** means the plan claim/requirement is supported by the cited source or internally well-defined; it does not mean future behavior has run. **FAILED** means a concrete contradiction or missing integration contract. **UNVERIFIED** means an explicitly planned runtime/tool experiment with no current execution evidence.

| # | Specific checked claim | Result | Evidence / boundary |
|---|---|---|---|
| 1.1 | Baseline has no implemented application commands. | VERIFIED | Phase 1:16; `README.md:7`; current file inventory. |
| 1.2 | Backend composition uses `apps/backend/src/email_support/main.py`. | VERIFIED | Phase 1:33–39; `docs/03-codebase-summary.md:7–11`. Proposed CREATE paths agree. |
| 1.3 | Only health models/routes are needed; no service wrapper. | VERIFIED | Phase 1:20; `docs/04-code-standards.md:21`; scout:18–20. |
| 1.4 | Required health `status` is a closed `StrEnum` with wire value `ok`. | VERIFIED | Phase 1:20; scout:53; `docs/04-code-standards.md:12,18`. Contract proposal agrees. |
| 1.5 | Offline exporter imports the same app rather than using a running server. | VERIFIED | Phase 1:22; scout:55. Explicit proposed data flow. |
| 1.6 | Python 3.13/uv exact versions and selected dependencies work together. | UNVERIFIED | Phase 1:50 and 88 explicitly gate this; scout:24,38,62 has observations only. |
| 1.7 | Source-layout backend is normally installed rather than relying on `PYTHONPATH`. | VERIFIED | Phase 1:30,50 defines package metadata and installation requirement; actual packaging still to implement. |
| 1.8 | Red HTTP/model tests must fail on behavior after the runner works. | VERIFIED | Phase 1:51; `docs/04-code-standards.md:38,52`. No false claim that import failure is meaningful red. |
| 1.9 | Owned source/scripts/tests are included in strict Python checks. | VERIFIED | Phase 1:56,74,84; `docs/04-code-standards.md:7–9`. Proposed gate covers exporter and tests. |
| 1.10 | Sorted export is byte-stable and snapshot matches the actual schema. | UNVERIFIED | Phase 1:52,57,83 prescribes the check; no exporter/artifact exists at baseline (`README.md:7`). |

## Checked claims — phase 2 (10)

| # | Specific checked claim | Result | Evidence / boundary |
|---|---|---|---|
| 2.1 | Input path `../backend/openapi.json` resolves from `apps/web/`. | VERIFIED | Phase 2:20; phase 1:42; scout:43. Proposed producer/consumer paths agree. |
| 2.2 | Runtime Zod validation is explicitly wired into generated SDK responses. | VERIFIED | Phase 2:20,62; scout:55; `docs/02-system-architecture.md:25`. Requirement is explicit; execution is pending. |
| 2.3 | Exact Hey API/Zod/TS package combination compiles and validates under Node 24. | UNVERIFIED | Phase 2:56,62,98; scout:30–38,47,62. Metadata is not execution proof. |
| 2.4 | Fetch plugin ID is retained without requiring deprecated standalone package. | VERIFIED | Phase 2:56; scout:36,47. Actual generated imports are an explicit discovery gate. |
| 2.5 | Generated source remains under all three requested strict compiler flags. | VERIFIED | Phase 2:35,62,69,91; `docs/04-code-standards.md:7`. No generated typecheck escape is authorized. |
| 2.6 | Query owns server state; no redundant payload definitions or store. | VERIFIED | Phase 2:24; `docs/02-system-architecture.md:25`; `docs/04-code-standards.md:14`. |
| 2.7 | Host and Compose proxy destinations preserve the same `/api/health` path. | VERIFIED | Phase 2:22; scout:54; phase 3:20. Browser never receives internal Compose DNS. |
| 2.8 | Tests exercise the generated operation, including malformed success, instead of isolated schema parsing. | VERIFIED | Phase 2:57–58; scout:55,57; `docs/04-code-standards.md:38`. Clear consumer-level acceptance. |
| 2.9 | Timeout/cancellation and HTTP/JSON/network failure actually settle visibly. | UNVERIFIED | Phase 2:24,57,63,100; `docs/04-code-standards.md:26`. Required tests exist only as proposals. |
| 2.10 | Unit and Playwright suites have non-overlapping discovery as later files arrive. | FAILED | Phase 2:39,64 lacks isolation; phase 3:36 adds a default Vitest match. Finding 1. |

## Checked claims — phase 3 (10)

| # | Specific checked claim | Result | Evidence / boundary |
|---|---|---|---|
| 3.1 | Compose is development-only API/web, loopback host publishes, internal all-interface binds. | VERIFIED | Phase 3:20; scout:54,58; scope at scout:18. Configuration validation remains future work. |
| 3.2 | Browser success uses actual API/proxy with no success interception. | VERIFIED | Phase 3:22,98; scout:57. No fake runtime behavior is authorized. |
| 3.3 | Startup and cleanup are bounded and ownership-aware. | VERIFIED | Phase 3:22,51,57,60,107. Requirements include failure cleanup; implementation pending. |
| 3.4 | CI is PR/main, read-only, no secrets, hosted runners, no skipped required jobs. | VERIFIED | Phase 3:24,109; `docs/04-code-standards.md:43`; no production authority is assumed. |
| 3.5 | Regenerate-then-status rejects all directly modified/deleted/untracked probe fixtures. | FAILED | Phase 3:52 versus 59; regenerating can repair/remove fixtures. Finding 2. |
| 3.6 | Scoped Git status covers staged changes and untracked output; plain diff is insufficient. | VERIFIED | Phase 3:59; scout:56. Subject to the probe correction above. |
| 3.7 | Existing baseline and separate review rules are correctly described. | VERIFIED | Phase 3:16; `.github/rulesets/main.json:5,12–27`; `.github/rulesets/review.json:5–10,20–34`. Live equality is not reverified here. |
| 3.8 | Required checks are selected only after emitted check discovery and before merge. | VERIFIED | Phase 3:65–68; `docs/04-code-standards.md:43,59`; scout:46. Exact names remain discoveries. |
| 3.9 | Owner retains final acceptance, closure, merge, deployment, release decisions. | VERIFIED | Phase 3:69,118; `AGENTS.md:5–7`; plan index:49. |
| 3.10 | Clean clone, Compose smoke, final-head hosted checks, applied ruleset, and post-merge run have passed. | UNVERIFIED | Phase 3:95–102,115–118 are future gates; `README.md:7`; scout:60–62. The plan correctly does not claim they passed. |

## TDD and scope verdict

Phases 1 and 2 define meaningful behavioral red/green sequencing, while allowing the runner and generated imports to exist before behavioral red. This is compatible with the requested TDD scope. Phase 3's real-browser failure-first sequence is concrete; its drift fixture setup needs correction before it can establish the advertised red evidence. The plan provides explicit boundaries for strictness, SDK validation, cancellation, generated ownership, cleanup, and owner acceptance; no generic service, storage/auth scaffold, or alternative generator is needed to fix the findings.

No implementation completeness or coverage percentage is claimed. All phase tasks remain proposed; final package compatibility, actual generated inventory, browser execution and emitted GitHub checks must be evidenced during implementation.

## Recommended actions

1. Assign explicit unit/E2E discovery settings and ownership before the phase 3 spec is created.
2. Specify reproducible drift fixtures whose regeneration creates observable Git changes; preserve the intended CI semantics.
3. Keep the existing early compatibility and actual generated-operation validation gates. Do not replace them with metadata-only claims.

## Unresolved questions

None requiring an owner product/architecture decision. Implementation must discover compatible exact versions, generated files, and GitHub check contexts, as already stated in the plan.

Status: DONE_WITH_CONCERNS
Summary: Reviewed all four plan files and 30 phase-specific claims. Found one High integration omission in test discovery and one Medium contradiction in drift probe semantics; both have bounded fixes within the accepted scope.
Concerns/Blockers: Correct the two findings before treating the plan as execution-ready; no runtime verification was performed.

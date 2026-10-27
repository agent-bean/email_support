---
title: "Phase 1: Evaluation contracts and runner — Issue #32"
status: todo
priority: P1
effort: "4–6 engineering days"
dependencies: []
---

# Phase 1: Evaluation contracts and runner

<!-- Updated: Owner-approved red-team R1/R3 - outbound privacy cases and compatible synthetic addresses. -->

## Outcome, ownership and prerequisites

Deliver the runnable #32 foundation before provider/workflow implementation. This PR owns evaluation contracts, authored corpus, evaluator, result review and command entry point. It does not claim a passing assistant. Read [evaluation requirements](../../docs/09-evaluation.md), [standards](../../docs/04-code-standards.md), [source map](../reports/scout-261027-1319-briefing-evaluation.md) and [workflow research](../reports/researcher-261027-1322-workflow-evaluation.md). Work on a fresh #32 branch from updated main after plan acceptance; no paid calls or database mutation is needed for this phase.

Existing command roots are explicit in `Makefile:30–39` and `apps/backend/pyproject.toml:35–52`; evaluation is not yet implemented. Both mypy root lists must include `evals`. Quality evaluation stays separate from pytest correctness tests. Existing wheel packaging at `apps/backend/pyproject.toml:32–33` only includes product source: keep `python -m evals` repository-local rather than accidentally publishing fixtures.

## Data flow and minimal contracts

1. A versioned dataset manifest loads candidate cases and verified permitted public source excerpts. Pydantic validates unknown JSON once, with closed statuses, `extra="forbid"`, aware timestamps, UUIDs and bounded values.
2. Cases record fixed clock/timezone, synthetic labels, explicit normalized email/meeting inputs with expected identity or unresolved ambiguity, source snapshot hashes/URLs/retrieval/publication time, expected atomic facts/evidence, forbidden outcomes and applicable feature checks. Unknown publication time stays null.
3. Replay loads previously captured typed outputs; an injected live invocation seam will later call the same production graph factory. Until phase 4 supplies it, live graph evaluation explicitly reports unsupported; no evaluation-only assistant is built.
4. Evaluators emit deterministic contract/safety outcomes and separate semantic review tasks. A model's fact ID, citation, confidence or support label is untrusted. IDs and source existence prove reference integrity, never arbitrary prose entailment.
5. A reviewer supplies claim/evidence support labels and meeting-usefulness/task-outcome assessments against the exact result/source hashes. New live claims stay `pending_human_review`. Golden expectations require an explicit owner-reviewed record bound to case/dataset/source hashes; generated output never promotes itself.
6. A result records per-case status, claim support, unknowns, task outcome, usefulness, elapsed time, attempts, retries and reported usage/cost, application revision, dataset/source/prompt/model/config identities and execution mode. Unknown measurements stay null; aggregate known attempted usage across retries separately from terminal attempt usage, never invent prices or cost from missing reports.

Use a small shared product claim/evidence contract in `models/briefing.py` so later production output and evaluator consumption share a type. Distinguish factual claims, stated needs, meeting statements, suggestions/questions and unknowns. Application validation prevents a factual assertion from evading review by merely attaching a model-chosen supported label; human review assesses semantic misclassification too.

Case status and check applicability are distinct: candidate/unreviewed, reviewed, unsupported-feature, failed and review-pending must survive aggregation. Unsupported and unreviewed entries are excluded from pass denominators and reported by count/reason. Establish measured baselines before any owner-selected thresholds; this phase invents none.

## File inventory

Inventory paths are relative to the repository root; create package `__init__.py` only for the new Python packages actually listed. No deletions.

| Action | File | Responsibility |
|---|---|---|
| Create | `apps/backend/src/email_support/models/briefing.py` | Shared claim/evidence/result boundary, with no graph dependency. |
| Create | `apps/backend/evals/__init__.py` | Evaluation package. |
| Create | `apps/backend/evals/__main__.py` | Strict argparse entry point, no implicit live calls. |
| Create | `apps/backend/evals/models.py` | Dataset, review, execution and result contracts. |
| Create | `apps/backend/evals/evaluators.py` | Reference/safety checks and human support/usefulness review binding. |
| Create | `apps/backend/evals/runner.py` | Replay, self-check, capability seam and sanitized reporting. |
| Create | `apps/backend/evals/datasets/briefing-v1/cases.json` | Ten-scenario candidate corpus with expected/forbidden outcomes. |
| Create | `apps/backend/evals/datasets/briefing-v1/sources.json` | Verified public provenance and permitted hashed excerpt snapshots. |
| Create | `apps/backend/evals/fixtures/evaluator-oracle.json` | Authored supported/unsupported evaluator contract fixture. |
| Create | `apps/backend/tests/unit/evals/test_evaluation_contracts.py` | Validation, source/review binding and safety failures. |
| Create | `apps/backend/tests/integration/test_evaluation_cli.py` | Real subprocess self-check, replay and malformed input reporting. |
| Modify | `apps/backend/pyproject.toml` | Add evals to explicit strict mypy roots; keep pytest scope. |
| Modify | `Makefile` | Add evals to invoked mypy roots. |
| Modify | `.gitignore` | Ignore private local evaluation results. |
| Modify | `docs/09-evaluation.md` | Implemented command/review/status ownership and gaps. |
| Modify | `docs/03-codebase-summary.md` | Actual eval module navigation. |

Read existing files before editing them. Phases 3/4 later own sequential extensions to `models/briefing.py`, `evals/runner.py`, `evals/models.py` and documentation; no simultaneous ownership.

## Tests Before — RED

Write unit and subprocess tests first; execute and retain failures caused by absent behavior, then implement. No expected-failure decoration conceals missing features.

| Scenario | Level | Required observation |
|---|---|---|
| Invalid case ID/version/timezone, duplicate source IDs, hash mismatch, unsupported check name | Unit | Validation fails with a safe actionable category. |
| Missing publication date; synthetic email at reserved example.com/net/org | Unit | Unknown date is retained; addresses pass the unchanged canonical validator, have no delivery capability or operational-address mapping, and use only the reserved fixture domains. |
| Source URL exists but text does not entail a claim; generated fake fact ID | Unit | Reference checks cannot mark semantic support; claim remains pending review or fails integrity. |
| Oracle supported vs unsupported assertion | Unit + CLI | Exact production evaluator distinguishes authored labels and exits nonzero if its self-check is deliberately inverted. |
| Candidate/golden transition; changed snapshot after review | Unit | No automatic promotion; missing owner review or stale hash rejects golden use. |
| Unsupported, unreviewed, missing usage, retry usage | Unit | Correct denominator/statuses; unknown remains unknown; attempted totals differ from terminal usage. |
| Injection/approval/delivery claims in a replay file | Unit | An artifact cannot grant authority; evaluators check observed events only and never dispatch effects. |
| Repeat replay with fixed clocks/sources | Subprocess | Same substantive results/config identity; wall-clock performance fields remain observational. |
| Full corpus inventory | Integration | All ten scenarios load, including unsupported later capabilities. |

## Implementation steps and refactor

1. Define dataset/result/review contracts and a minimal typed invocation interface without importing planned graph code. Keep business types in product models, evaluation bookkeeping in evals.
2. Verify real public company source URLs manually during corpus authoring, record retrieval time and publication time only if known, retain permitted minimal excerpts with cryptographic hashes and source version. Do not fill the corpus with invented company facts or claim URLs were checked when they were not. Source retrieval is read-only; synthetic meetings/needs remain explicitly fictional.
3. Populate all ten scenario groups below. Variants may share sources but must isolate intended failures. Each has inputs, expected facts/evidence, forbidden outcomes and applicable checks. Start as candidate; collect owner review before golden designation. Use reserved example.com/net/org synthetic addresses compatible with the unchanged canonical email validator; the runner has no send capability, credentials or mapping to operational inboxes. Validate that exact reserved-domain set at the corpus boundary; do not relax production address validation.
4. Implement reference integrity and event-based deterministic checks; keep semantic support/usefulness pending human review unless bound review annotations exist. The evaluator oracle uses developer-authored contract labels and exact records, labelled `evaluator-oracle`, not owner-golden company data or evidence of model quality.
5. Implement runnable self-check and offline captured-output replay. The self-check runs production evaluators and aggregators, not a special function returning fixed success. Keep live invocation opt-in and unsupported until its production adapter exists.
6. Implement versioned structured output and explicit review ingestion. Reject review files bound to another run/source/content hash. Keep full inputs/source contents in protected isolated storage; default tracked summaries contain sanitized aggregate metrics, IDs and hashes only.
7. Refactor common validation/report aggregation behind those tests. Update both static-check roots and the smallest owning docs only once commands exist and have been exercised.

## Corpus coverage and later boundaries

| Scenario group | Initial handling / later integration |
|---|---|
| New company/upcoming meeting | Expected no invented relationship history; graph execution becomes available in phase 4. |
| Returning company/approved knowledge | Same-company approved sources and wrong-company/revoked exclusion; phase 4 canonical retrieval. |
| Irrelevant email | No unnecessary research/delivery expectation recorded; classifier becomes available through phase 3 (#8), unsupported until then. |
| Ambiguous identity/correction | Phase 3 interprets identity candidates and persists explicit owner corrections; phase 4 stops research while ambiguity remains. |
| Missing/cancelled meeting | Explicit absence/cancellation, no invented meeting/attendance; phase 4. |
| Missing/stale/conflicting evidence | Dates/unknowns retained; phase 4. |
| Injection in email/page/attachment | Record forbidden outbound disclosure of private canary text through queries/URLs, as well as forbidden effects. Phases 2/4 exercise actual executor events and public-input isolation; attachment extraction itself remains unsupported. |
| Approved version/recipient edits | Fixture specifies binding invariant; feature-level evaluation unsupported until approval interface exists. Existing deterministic persistence tests remain authoritative. |
| Uncertain delivery/restart | Workflow restart is phase 4; delivery reconciliation remains unsupported, with no pretending an absent sender passed. |
| Attachments/exports | Required facts/provenance/version equivalence defined; execution unsupported in this slice. |

## Tests After — GREEN and verification

These are **proposed new commands**, unavailable until implemented, run from `apps/backend`:

```sh
uv run --locked pytest -q tests/unit/evals/test_evaluation_contracts.py tests/integration/test_evaluation_cli.py
uv run --locked python -m evals self-check
uv run --locked python -m evals validate --dataset evals/datasets/briefing-v1
uv run --locked python -m evals replay --dataset evals/datasets/briefing-v1 --results PATH_TO_CAPTURED_RESULTS --output PATH_TO_PRIVATE_OUTPUT
```

Run narrow tests first, then existing root `make backend-check`; it must include evals in mypy. Test invalid oracle input/negative process exit as well as successful invocation. No live-quality metric is established by these commands. No tests were run while drafting this plan.

## Acceptance mapping — Issue #32

- [ ] AC1: typed case/evaluator/result models and a runnable documented entry point pass validation/subprocess tests.
- [ ] AC2: inventory proves all ten scenario groups, inputs, facts/evidence, forbidden outcomes and applicable checks exist.
- [ ] AC3: real source verification evidence, fixed clocks, hashed snapshots, synthetic labels and non-deliverable addresses are inspected.
- [ ] AC4: review binding rejects auto-golden/stale expectations; unreviewed and unsupported cases never pass.
- [ ] AC5: replay/live modes and result identities/metrics exist; unavailable live adapter reports unsupported, unknown usage remains null.
- [ ] AC6: production evaluator self-check distinguishes oracle labels; deterministic safety checks cannot authorize effects; tracked artifacts contain no credentials/private content.

## Risks, security, compatibility and rollback

| Risk | Likelihood × impact | Mitigation |
|---|---|---|
| False factual confidence from IDs/string matching | High × High | Reference integrity and semantic review are separate; fresh prose requires human claim/evidence assessment. |
| Unsupported scenarios disappear from denominator | Medium × High | Inventory and aggregate status regression tests. |
| Unreviewed baseline or stale source is promoted | Medium × High | Owner review tied to immutable dataset/source hashes; no automatic baseline rewrite. |
| Copyright/private content enters fixtures or results | Medium × High | Permitted minimal public excerpts, synthetic inputs, private output directory, sanitized tracked summaries. |
| Scope expands into later features | Medium × Medium | Keep case expectations but report unsupported feature checks. |

This is additive and changes no API/schema or operational data. Roll back the PR and ignored local results; retain source/review records needed to interpret any already captured output. Never relabel old results under a changed dataset version. Handoff only after separate review, required checks, owner acceptance and merge authorization; phase 2 then consumes the accepted contracts. Unresolved evidence: verified source selection and owner golden reviews are implementation tasks, not facts established by this plan.

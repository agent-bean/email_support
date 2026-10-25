# Security and contract plan review

Scope: issue #2 plan only, `--yagni --hard --tdd`. Reviewed all four original plan files, repository AGENTS.md, architecture/code/deployment standards, both checked-in rulesets, and the controller scout. No application commands, installations, GitHub mutations, or runtime checks were performed. Proposed files and commands were assessed as proposals.

## Findings

### Medium — Drift probes can be erased by the operation under test

- Plan evidence: `plans/261024-1819-issue-2-typed-foundation/phase-03-local-runtime-ci-and-handoff.md:52` requires the drift script to fail for a modified generated file and a deleted tracked generated file. At `:59`, the script first exports and generates, then checks Git porcelain status. The acceptance table repeats the expected failure at `:96`.
- Repository contract: `docs/04-code-standards.md:38` requires tests that prove the invariant; `:43` requires generated OpenAPI drift coverage. `docs/02-system-architecture.md:25` makes generated artifacts derive from backend OpenAPI. `README.md:7` confirms these are future implementation requirements, not defects in existing application code.
- Failure: starting from a clean committed tree, alter or delete an output that deterministic generation rewrites or recreates, then invoke the script. Regeneration restores the committed result, leaving clean status and an expected successful script exit. The proposed experiment therefore cannot reliably establish the claimed negative oracle. An executor could spend time forcing a correct regeneration path to fail or record misleading evidence.
- Smallest correction: distinguish detector probes from end-to-end drift probes. Inject modified/deleted/untracked files after regeneration when testing the status detector. Separately change an input contract in a disposable checkout while retaining committed old outputs; run the complete script and require nonzero exit for resulting generated differences. Keep clean committed regeneration as the positive case. Do not require a repaired output-only mutation to remain a failure.

## Security boundary verification

No Critical or High finding was verified in this plan scope.

- Untrusted CI explicitly uses `pull_request`, GitHub-hosted runners, read-only contents permission, immutable action SHAs, no secrets/deployment environment, and timeouts (`phase-03-local-runtime-ci-and-handoff.md:24`, `:60`, `:109`). No cache design is proposed; no cache finding is inferred.
- Host defaults and Compose loopback publishing are explicit, while container listeners bind internally for service-DNS proxy access (`phase-02-generated-web-contract.md:22`; phase 3 `:20`). This does not require production authentication, rate limiting, or public-edge controls for a credential-free liveness response.
- Required-check discovery and application occur before merge, with final-head rechecks and owner-controlled merge (`phase-03-local-runtime-ci-and-handoff.md:65–69`). This matches `docs/04-code-standards.md:43`. Empty baseline bypass actors and separate review exceptions are preserved (`.github/rulesets/main.json:5`, `:12–27`; `.github/rulesets/review.json:5–10`, `:27–30`; standards `:59`). Live rule equality and emitted source inspection remain implementation gates, not verified live state in this review.
- Generated validation false-success is directly addressed: explicit SDK Zod response validation and malformed-payload tests through the actual generated operation, plus UI assertions and a real browser/API smoke (`phase-02-generated-web-contract.md:20`, `:24`, `:57–58`; phase 3 `:22`). A standalone schema test is explicitly insufficient.

## Plan status and limits

Keep all phases pending. The review establishes plan consistency only; actual pinned dependency compatibility, generated behavior, hosted CI permissions/check identities, live ruleset application, and runtime exposure require the implementation evidence already assigned by the plan. No extra production or provider scope is recommended.

## Unresolved questions

None requiring an owner decision.

Status: DONE_WITH_CONCERNS
Summary: One Medium verification defect needs a narrow clarification to the drift experiments. No additional security blocker was verified within the credential-free health API/web threat model.

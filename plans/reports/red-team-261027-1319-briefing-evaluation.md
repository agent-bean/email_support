# Joint plan red-team review

Scope: #32 → #9 → #8 → #13. Flags: `--tdd --hard --yagni`. Planning review only. The owner subsequently answered “Áp dụng tất cả (khuyến nghị)” to all three proposed fixes and the citation correction. All are applied to plan files; no application files changed. Evidence line numbers below refer to the reviewed pre-fix draft and remain historical review anchors.

## Security Adversary

Verified 12 concrete claims, three per phase: eval packaging/static-check roots (`apps/backend/pyproject.toml:32–51`, `Makefile:30–35`); existing HTTPX2 dependency/client/timeout (`apps/backend/pyproject.toml:19`, `integrations/google_workspace.py:12,85–89`); contact email uniqueness, nonunique companies and closed evidence sources (`storage/postgres/persistence/tables/core.py:53–100,243–277`, `models/persistence/core.py:168–200`); non-idempotent version creation, nullable-company knowledge filtering and completed approval semantics (`storage/postgres/persistence/core.py:329–369`, `storage/postgres/persistence/decisions.py:188–206`, `storage/postgres/persistence/tables/decisions.py:26–62`). Source paths in this paragraph are relative to `apps/backend/src/email_support/` unless prefixed otherwise.

| ID | Severity | Finding and evidence | Proposed disposition |
|---|---|---|---|
| R1 | High | Model-controlled search/fetch can transmit private context to public destinations. Phase 2 lines 21–22,28–30 and phase 4 lines 28–30 define read-only tools and SSRF controls but no public-input/query/URL provenance boundary. Private content actually exists in `apps/backend/src/email_support/models/persistence/core.py:72–82` and `apps/backend/src/email_support/models/persistence/decisions.py:79–88`. | Accepted by owner; applied to plan. Define minimal public research inputs, exclude raw private mail/meeting/knowledge from research context, allow queries from explicitly public identifiers/topics and fetches from controlled source references. Test private canary exclusion from outbound destinations/payloads. Preserve private needs for synthesis behind its own boundary. |
| R2 | High | Recovery may resume context loaded before owner invalidation. Phase 4 lines 29–33,59–61 checks identity/input but does not recheck referenced knowledge eligibility at recovery/final binding. `apps/backend/src/email_support/storage/postgres/persistence/decisions.py:188–206` filters only at query time; `:224–233` invalidates later and `:181–185` retrieves sealed items without an eligibility check. Failure reviewer independently confirms conflict with immediate exclusion in `docs/02-system-architecture.md:51,55`. | Accepted by owner; applied to plan. Retain referenced knowledge IDs/version identities; revalidate company and eligibility on recovery and before binding, with ordering against concurrent invalidation. Stop/recompute affected context; preserve historical sealed drafts. Add real-DB crash→invalidate→recover and invalidation/binding race scenarios. |

## Assumptions and scope

Twelve claim samples checked (three per phase), including explicit mypy roots, pytest/wheel scope, HTTPX2 dependency/construction, contact uniqueness and nullable mapping, closed source variants, version creation, completed approval semantics and nullable-company filtering. These overlap the security ledger and are not 12 additional unique claims. No substantiated complexity blocker: normalized inputs address genuine provenance constraints, and run binding addresses non-idempotent version creation.

| ID | Severity | Finding and evidence | Proposed disposition |
|---|---|---|---|
| R3 | Medium | Phase 1 lines 62/75 prescribes `.invalid` addresses, while phase 3 lines 23/78 retains canonical email validation. `apps/backend/src/email_support/models/persistence/common.py:30–36` calls email-validator without a special-use allowance; `models/persistence/core.py:56–61` applies it to contacts. Existing fixture `apps/backend/tests/unit/persistence/core/test_core_persistence_contracts.py:24` uses example.com. | Accepted by owner; applied to plan. Use reserved example.com/net/org synthetic addresses accepted by the unchanged validator; keep isolated synthetic data, no delivery capability and no operational-address mapping. Propagate across all phases/corpus instructions. |

Controller verified R3 against locked email-validator 2.3.0 (`apps/backend/uv.lock:215–216`) and its [tagged special-use list](https://github.com/JoshData/python-email-validator/blob/v2.3.0/email_validator/__init__.py#L41-L68) plus [rejection logic](https://github.com/JoshData/python-email-validator/blob/v2.3.0/email_validator/syntax.py#L578-L588). This is source verification, not a runtime reproduction. Installed dependency source read was blocked by the workspace hook; no ignore rule was changed and no test was run.

Administrative correction proposed alongside R3: phase 2 line 15 points to `google_workspace.py:342–353` for client construction, but its actual constructor is `:85–89` (import `:12`). Update that citation; behavior description is accurate.

## Failure modes

Sixteen samples checked (four per phase): packaging/static roots; separate correctness/evaluation; review/unknown/unsupported accounting; HTTPX2/client; allowlists and usage; contact uniqueness/company nullability/source constraints; version idempotency, approvals, nullable company query and whole-DB backup/canonical metadata (`apps/backend/scripts/test_database.py:601–632`, `apps/backend/migrations/env.py:18,44–52`). These overlap earlier samples. Independently confirmed R2, deduplicated; no additional evidence-backed finding. Separate-saver races and runtime compatibility remain explicit stop gates, not assertions of solved behavior.

## Controller adjudication and gate

Three unique findings: two High and one Medium. All pass codebase-evidence filtering; proposed Accept 3, Reject 0. One duplicate R2 was merged. Forty total claim samples were checked across reviewers, including overlap, plus the controller's locked-version source check. The incorrect citation is a verification failure to correct, rather than a separate product risk. Proposed future APIs and filenames are not missing-current-code failures.

Owner disposition: Accept all three and the citation correction. The earlier table records the proposal at review time; its pending wording is superseded by this explicit decision. Applied R1 through phases 2/4 and phase-1 adversarial expectations, R2 through phase 4 context/run requirements, transaction ordering, tests, acceptance and risk notes, and R3 through all four phases. Corrected the phase-2 source citation. No new scope or implementation authorization is inferred.

### Decision deltas

- R1: research receives only operator-approved public identifiers/topics; application builds queries and resolves controlled source references. Private context remains in synthesis without web tools. Outbound canary tests use actual executor/transport observations.
- R2: retain canonical knowledge dependency identities; revalidate on recovered-context consumption and final binding. Stable row-lock ordering serializes binding with invalidation; stop stale runs, preserve sealed history and expose it as non-current.
- R3: reserved example.com/net/org fixture addresses retain canonical validator behavior, isolated evaluation and no delivery capability/mapping. The previous special-use suffix is no longer an executable instruction.
- Citation: client construction points to google_workspace.py:85–89 instead of response handling.

### Whole-Plan Consistency Sweep

Completed after applying the decision deltas: re-read the index and all four phase files; reconciled data flow, executor contracts, stored dependency references, ownership/transaction rules, acceptance, tests, risks and recovery behavior. Source checks confirm the existing invalidator performs a row update and the client constructor uses explicit timeout/disabled redirects. R2 checks also cover the pending-review node and canonical-first authority summary.

No obsolete fixture suffix or incorrect client-construction citation remains in executable phase instructions. Historical evidence above is explicitly labelled pre-fix. No dependency bypass or #8 exclusion remains authoritative. All local plan links resolve, phase dependencies are acyclic and sequential, frontmatter is valid, and no implementation acceptance checkbox is checked. `ak plan validate` passes. Unresolved contradictions: 0. Runtime/provider compatibility, live-quality evidence, real-DB concurrency/recovery and human dataset review remain implementation gates, not completed checks. Owner plan approval remains pending.

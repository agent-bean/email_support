---
title: "Briefing evaluation, research tools, company identity and resumable workflow"
description: "Deliver Issues #32, #9, #8 and #13 through four sequential reviewed PRs."
status: pending
priority: P1
effort: "22–33 engineering days; excludes owner review and credential wait"
branch: fix/issue-6-verification
tags: [feature, backend, database, evaluation]
created: 2026-10-27
---

# Joint briefing and evaluation plan

## Outcome and contract

A developer runs explicit normalized email/meeting inputs, resolves company identity, and proceeds through bounded real research, obtains a cited immutable Markdown briefing paused for review, and measures support/usefulness with honest coverage. Flags: `--tdd --hard --yagni`. The owner explicitly approved this plan on 2026-10-27. Implementation has not started; issue acceptance, merge and release remain separately authorized gates.

The owner accepted one plan and four sequential PRs, #32 → #9 → #8 → #13. Each requires its own review, checks, explicit owner acceptance and merge authorization before the next PR proceeds. Use new issue branches from updated `main`; the frontmatter branch records planning provenance only.

The owner added full #8: relevance interpretation, stable contact/company resolution and persistent explicit owner corrections precede #13 research. This supersedes the earlier proposal to stage #13 before #8. Ambiguity stops. No UI/API routes, scheduler, synchronization, sending, promotion, projections, attachments/exports, or full #10/#14/#15/#19/#20 implementation enters this slice. #13 ends at pending review; authenticated decision/resume belongs to #14.

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Evaluation contracts and runner — #32](./phase-01-start.md) | Pending |
| 2 | [Bounded provider tools — #9](./phase-02-provider-tools.md) | Pending |
| 3 | [Email interpretation and identity — #8](./phase-03-email-interpretation-and-identity.md) | Pending |
| 4 | [Resumable briefing and live evaluation — #13](./phase-04-resumable-briefing-and-live-evaluation.md) | Pending |

Phase files own executable steps, repo-relative file inventories, RED/GREEN scenarios, risks, rollback and criterion mappings. Estimates: 4–6, 5–7, 5–8 and 8–12 engineering days respectively. Files are owned sequentially; no parallel edits or migration allocation.

## Dependencies

- #32 native blockers #2/#31 and #9 blocker #2 are closed. #9 depends on accepted #32 contracts in this delivery sequence.
- #8 depends on #9/#32 and closed #3. #13 depends on #8/#32. The four-PR sequence satisfies existing native blockers naturally; no dependency bypass or GitHub mutation is needed.
- Phase 2 needs configured gateway/OpenRouter/Tavily credentials and connection-safe fetching proof. Phase 4 needs compatible locked LangGraph/Psycopg/Python 3.13 APIs, guarded PostgreSQL bootstrap and reviewed applicable evaluation cases. Missing prerequisites remain visible blockers to the corresponding evidence gate.

## Acceptance

- [ ] #32: validated runnable corpus/runner represents all ten scenarios, verifies source provenance, separates candidate/golden/unsupported statuses, and passes its evaluator oracle self-check.
- [ ] #9: typed read-only tools enforce permissions, budgets and public-only query/source provenance; fetch fails closed unless the actual connection is vetted; genuine smoke records gateway/tools/schema/usage and search/embedding capabilities.
- [ ] #8: typed interpretation separates relevance/needs/candidates; repeated identities stay stable, ambiguity never silently merges, and durable owner corrections control future lookups.
- [ ] #13: the shared production graph persists one sealed version and pending review per run; restart, concurrent ownership and revoked-knowledge recovery/binding ordering are proven; private synthesis context stays outside web research; reviewed applicable live cases record support and human usefulness.
- [ ] No replay, unreviewed claim or unsupported feature is counted as a live-quality pass; missing usage/cost remains unknown; no full-release claim is made.
- [ ] Each PR has actual verification evidence, separate review/acceptance/merge gates, minimal owning docs updates and safe rollback evidence.

## Evidence and planning gates

- [Source map](../reports/scout-261027-1319-briefing-evaluation.md)
- [Provider research](../reports/researcher-261027-1319-provider-tools.md)
- [Owner decision/validation record](../reports/validation-261027-1319-briefing-evaluation.md)
- [Workflow and evaluation research](../reports/researcher-261027-1322-workflow-evaluation.md)
- [Product and architecture navigation](../../docs/00-index.md); [evaluation authority](../../docs/09-evaluation.md).

## Red Team Review

The owner approved all three findings (two High, one Medium) and the citation correction, then explicitly approved the complete plan on 2026-10-27. Applied public research isolation, canonical knowledge eligibility checks and compatible reserved example-domain fixtures; [adjudication and evidence](../reports/red-team-261027-1319-briefing-evaluation.md). Forty overlapping claim samples checked. No application tests, providers, database changes or implementation commands were run while drafting.

### Whole-Plan Consistency Sweep

Re-read all five files after propagation; reconciled requirements, steps, tests, acceptance and risks. No superseded fixture/citation instructions or unresolved contradictions remain. Local links, phase dependencies and CLI format validation pass; [verification record](../reports/validation-261027-1319-briefing-evaluation.md). Plan is owner-approved and ready for execution through cook.

## Open evidence

Gateway capabilities, address-pinning compatibility, exact dependency pins, verified corpus sources and human baseline reviews must be established during their specified phase gates. These are execution evidence requirements, not a new scope decision.

<!-- slug: issues-32-9-8-13-briefing-evaluation -->

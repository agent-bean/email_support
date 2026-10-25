---
title: "issue-24-project-status-automation"
description: "Keep Issue status accurate with native PR linking, an AI-operated helper, and Project auto-close."
status: completed
priority: P1
effort: ""
tags: [github, workflow]
created: 2026-10-24
---

# GitHub Project status automation

## Overview

Make Project #15 reflect the selected Issue's delivery state. Native PR linking moves the Issue to `Review`; AI uses the safe status helper for requested changes, verification, and post-merge completion. Project Auto-close closes the Issue after AI sets `Done`. The Issue remains the only Project item.

## Goals

| # | Goal | Priority |
|---|------|----------|
| 1 | Keep Issue status aligned with delivery state using native PR linking and AI-operated transitions. | P1 |

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Phase 1: Project status command](./phase-01-start.md) | Done |
| 2 | [Phase 2: Project status workflow](./phase-02-native-project-automation.md) | Done |

## Success Criteria

- [x] The status helper changes only one matching Issue's Status and fails without mutation when the Issue or target status is missing or ambiguous.
- [x] Owner-selected work moves to `Ready`; implementation and verification gaps move to `In progress`.
- [x] Future PRs use a native Issue link and are created with assignee, reviewer, labels, and milestone from the Issue.
- [x] The owning Issue has a GitHub Type (`Feature`, `Bug`, or `Task`); pull requests do not support Issue Type.
- [x] Project Auto-close closes an Issue at `Done`; no GitHub App or repository secret is needed.
- [x] Native PR linking moves the Issue to `Review`; a formal `Request changes` review leaves it there, and the status helper moves it to `In progress` before returning it to `Review` for re-review.
- [x] After approval and passing acceptance checks, AI moves the Issue to `Verify`; verification gaps remain documented as a return to `In progress`.
- [x] After owner acceptance and authorized merge, AI sets the existing Issue item to `Done` and Project Auto-close closes Issue #24 ([PR #26](https://github.com/agent-bean/email_support/pull/26); [post-merge CI](https://github.com/agent-bean/email_support/actions/runs/40173548882)).
- [x] Issue/PR text follows concise writing rules, Issue criteria use checkboxes, and the follow-up PR follows the shared form.
- [x] Changes stay limited to Issue #24, PR #25's description, and the linked follow-up PR; Issue #2 and PR #23 remain unaffected.

## Scope boundary

- Update Issue #24 and its workflow docs/templates only; do not change Issue #2 or PR #23.
- Do not create a second Project item for a PR.
- Keep the enabled Project `Pull request linked to issue` and `Auto-close issue` workflows; keep repository auto-close for merged linked PRs disabled.
- Do not change Project settings, add GitHub Actions or GitHub App credentials, or add a PR as a second Project item.
- AI observes PR review/merge events and uses the helper when native workflows do not update the existing Issue item.

<!-- slug: issue-24-project-status-automation -->

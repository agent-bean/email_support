---
title: "issue-24-project-status-automation"
description: "Automate future Issue status with a small CLI helper and native Project workflows."
status: in_progress
priority: P1
effort: ""
tags: [github, workflow]
created: 2026-10-24
---

# GitHub Project status automation

## Overview

Make Project #15 reflect the selected Issue's real delivery state. AI updates selection, implementation, and re-review states; native Project automations update linked PR review and merge states. The Issue remains the only Project item.

## Goals

| # | Goal | Priority |
|---|------|----------|
| 1 | Make safe status changes for the selected Issue and automate PR review/merge transitions for future work. | P1 |

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Phase 1: Project status command](./phase-01-start.md) | Done |
| 2 | [Phase 2: Native Project automation](./phase-02-native-project-automation.md) | In progress |

## Success Criteria

- [x] AI can set only an Issue's Status in Project #15; missing or ambiguous items/statuses fail without mutation.
- [x] Owner-selected work moves to Ready; implementation and failed verification move to In progress.
- [ ] Linking a ready-for-review PR moves the Issue to Review; requested changes move it to In progress; AI verifies acceptance before merge and returns gaps to In progress; merge moves the Issue to Done.
- [ ] AI reports evidence and waits in Verify before merge; explicit owner acceptance authorizes merge, after which AI closes the Issue.
- [x] Future PRs use a native Issue link and have assignee, reviewer, labels, and milestone set at creation.
- [ ] The owning Issue has a GitHub Type (`Feature`, `Bug`, or `Task`); pull requests do not support Issue Type.
- [x] Native Project automations are used without a GitHub App or repo secrets.
- [x] No pre-existing task Issue or PR is changed; changes are limited to Issue #24 and Project settings for future work.

## Scope boundary

- Only configure the workflow for future work. Do not change Issue #2, PR #23, or any other existing Issue/PR.
- Do not create a second Project item for a PR.
- Keep both the Project `Auto-close issue` workflow and repository `Auto-close issues with merged linked pull requests` setting disabled; do not close an Issue on merge.
- Do not add GitHub Actions, GitHub App credentials, or a second Project item; native Project workflows cover the PR event transitions.

<!-- slug: issue-24-project-status-automation -->

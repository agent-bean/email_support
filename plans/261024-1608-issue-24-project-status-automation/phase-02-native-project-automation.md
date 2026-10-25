---
title: "Phase 2: Project status workflow"
status: in_progress
---

# Phase 2: Project status workflow

## Overview

Keep Project #15 at one Issue item per task. Use its native linked-PR and auto-close workflows; use the safe status helper for transitions that PR-item workflows do not apply to the Issue.

## Requirements

- The enabled `Pull request linked to issue` workflow moves the linked Issue to `Review`.
- After a formal review requests changes, AI confirms the Issue status and moves it to `In progress` if the PR-item workflow did not update it; after fixes are ready, AI returns it to `Review`.
- After approval and passing acceptance checks, AI moves the Issue to `Verify`; any verification gap returns it to `In progress`.
- After owner-authorized merge, AI moves the Issue to `Done`; Project `Auto-close issue` closes it.
- The owning Issue has a GitHub Type (`Feature`, `Bug`, or `Task`); PR metadata is set at creation from the Issue.
- Keep repository auto-close for merged linked PRs disabled.
- Keep Issue/PR descriptions concise, without personal identifiers or duplicated GitHub metadata; Issue acceptance criteria use checkboxes and PR descriptions follow the shared form.
- Update only Issue #24, PR #25's description, and the authorized follow-up PR; leave Issue #2 and PR #23 unchanged.

## Files and Project settings

- `AGENTS.md`
- `.github/ISSUE_TEMPLATE/`
- `.github/pull_request_template.md`
- `docs/08-github-project-workflow.md`
- Issue #24 and PR #25 descriptions
- Project #15 linked-PR, review, merge, and auto-close workflows
- This phase plan and `plan.md`

## Implementation Steps

1. Verify the live Project workflows and repository auto-close setting; change neither setting in this phase.
2. Document that native PR linking moves the Issue to `Review`; AI checks and corrects Issue status for requested changes, verification, and post-merge completion because review/merge workflows update PR items.
3. Add concise Issue/PR writing rules, checkbox guidance and starters for Issue criteria, and a shared PR form without copied acceptance criteria.
4. Reopen Issue #24, link the ready follow-up PR natively, and verify the formal `Request changes` transition.

## Validation

- Verify `Pull request linked to issue` moves a linked Issue to `Review`, `Auto-close issue` closes it at `Done`, and repository auto-close for merged linked PRs remains disabled.
- Confirm Project #15 contains one Issue item for #24 and no separate PR item.
- Confirm Issue #24 is concise, has checkbox acceptance criteria, and contains no personal identifiers.
- Validate issue-form YAML and confirm the PR body follows the shared headings, reports only actual changes/checks, and uses checkboxes only for discrete validation results.
- Verify the follow-up PR is natively linked to Issue #24, has the configured metadata, and moves the Project Issue from `Review` to `In progress` after a formal `Request changes` review. Use the helper only if the native workflow did not change the Issue.
- After fixes are ready, return the Issue to `Review`; after approval and verification, leave it in `Verify` pending owner acceptance.

## Risk and rollback

- PR review/merge workflows may update PR items, while this Project intentionally keeps only the Issue. Check the Issue's actual status after each event and use the helper where needed. Project Auto-close closes it after AI sets `Done`; repository auto-close stays disabled.
- If a status transition is unexpected, inspect the review and Project item, then use the helper to restore the expected Issue status. No Project configuration changes are planned.

## Success Criteria

- Native linking sets the Issue to `Review`; a formal `Request changes` review leaves it there, so AI uses the helper to set `In progress` and returns it to `Review` when ready for re-review.
- After approval and passing acceptance checks, AI sets `Verify`; verification gaps return to `In progress`. After owner-authorized merge, AI sets `Done` and Project Auto-close closes the Issue.
- Issue/PR writing follows the concise shared rules, and no GitHub App or repository secret is needed.

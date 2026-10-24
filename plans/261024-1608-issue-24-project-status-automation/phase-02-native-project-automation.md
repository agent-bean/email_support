---
title: "Phase 2: Native Project automation"
status: in_progress
---

# Phase 2: Native Project automation

## Overview

Configure Project #15's native pull-request workflows so future linked PR events update the one owning Issue. Use AI status updates for selection, implementation, and re-review after requested changes.

## Requirements

- A ready PR linked to its owning Issue moves that Issue to `Review`.
- A review requesting changes moves it to `In progress`.
- AI moves a reviewed PR to `Verify` only after all acceptance checks pass; a verification gap returns the Issue to `In progress`.
- A merged, owner-accepted PR moves the Issue to `Done`; the Project `Auto-close issue` workflow closes the Issue.
- The owning Issue has a GitHub Type (`Feature`, `Bug`, or `Task`). Pull requests do not support Issue Type.
- PR metadata is set at creation: assign the configured developer account, request review from the configured tech lead, and copy labels and milestone from the owning Issue.
- Enable the Project `Auto-close issue` workflow to close Issues when Status changes to `Done`; keep the repository `Auto-close issues with merged linked pull requests` setting disabled.
- Do not change existing Issues or PRs.

## Files and Project settings

- `docs/08-github-project-workflow.md`
- `docs/00-index.md`
- `.github/pull_request_template.md`
- Project #15 workflows: `Pull request linked to issue`, `Code changes requested`, and `Pull request merged`
- This phase plan and `plan.md`

## Implementation Steps

1. Set the native `Pull request linked to issue` workflow to `Review` and enable it.
2. Set `Code changes requested` to `In progress` and enable it.
3. Set `Pull request merged` to `Done` and enable it. AI sets `Verify` before merge after acceptance checks pass.
4. Enable Project `Auto-close issue` for the `Done` status. Keep repository `Auto-close issues with merged linked pull requests` disabled so Issue closure follows the Project Status transition.
5. Add the workflow guide, index link, and PR template instructions for Issue Type, linking, metadata, re-review, pre-merge verification, and owner acceptance.

## Validation

- Verify each saved Project workflow visibly shows the required enabled state and target.
- Verify Project `Auto-close issue` is enabled for Status `Done` and repository auto-close for merged linked PRs remains disabled.
- Confirm Project #15 still contains one principal Issue item per task and no PR items were added.
- Review the PR template and workflow guide against Project #15 README and acceptance rules.
- Verify Issue #24 is typed `Feature`; verify native linking moves it to `Review`.

## Risk and rollback

- The native linked-PR workflow acts only when a PR is natively linked to an Issue. AI must link a PR only when ready for review; a draft stays unlinked until then. The native merge workflow sets `Done` regardless of current Status, so the Project auto-close workflow will close the Issue after merge. AI and the owner must enforce Verify and acceptance before merging; the repository auto-close setting remains disabled.
- If a native workflow behaves unexpectedly, disable only that workflow and restore statuses through the phase-1 command after inspecting the affected Issue.

## Success Criteria

- Native linking to a ready PR sets `Review`; requested changes set `In progress`; AI verifies before merge; merge sets `Done` and Project auto-close closes the Issue while repository auto-close stays disabled.
- After fixing requested changes, AI returns the Issue to `Review` when it requests review again.
- No GitHub App or repository secret is needed.

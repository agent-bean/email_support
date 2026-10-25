---
title: "Phase 1: Project status command"
status: done
---

# Phase 1: Project status command

## Overview

Add one repeatable command for AI sessions to update the selected Issue's Status in Project #15.

## Requirements

- Resolve the Project item, Status field, and option by repository, Issue number, and displayed name. Do not hard-code mutable Project field or option IDs.
- Require exactly one matching Issue item and fail before mutation when the Issue, Project item, field, or status is missing or ambiguous.
- Change only Status. Do not close an Issue as part of a status update.
- Do not alter Issue #2, PR #23, or other existing work.

## Files

- `scripts/project-status.sh`
- This phase plan and `plan.md`

## Implementation Steps

1. Implement the scoped status command for an Issue item.
2. Manually review the command's failure guards and confirm it changes only the Status field.

## Validation

- Inspect the Project item-list and field schema using read-only GitHub GraphQL/CLI queries.
- Manually review each failure guard; no test suite is included in this phase.

## Risk and rollback

- The command writes only one explicitly resolved Issue item's Status; ambiguous resolution stops before the write.
- Rollback by reverting the phase commit. Existing Project items remain unchanged.

## Success Criteria

- AI can use one relative-path command to set Ready, In progress, Review, Verify, Done, Backlog, or Dropped.
- Missing/ambiguous targets fail with a clear message; the command never closes an Issue.

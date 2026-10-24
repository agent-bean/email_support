# GitHub Project workflow

Email Support Project #15 keeps one execution item per task: the Issue. Pull requests are linked to that Issue through GitHub's native Development relationship and never become separate Project items.

## Status flow

```mermaid
flowchart TD
    Backlog -->|Owner selects a task; AI sets Ready| Ready
    Ready -->|AI starts implementation| InProgress[In progress]
    InProgress -->|PR is ready and natively linked| Review
    Review -->|Review requests changes| InProgress
    InProgress -->|AI finishes fixes and requests review again| Review
    Review -->|PR is merged| Verify
    Verify -->|A criterion is missing| InProgress
    Verify -->|Criteria pass; AI reports evidence and waits| Acceptance{Owner accepts?}
    Acceptance -->|Yes| Done
    Acceptance -->|No or gap found| InProgress
    Done -->|AI closes the Issue after acceptance| Closed
```

The Project's native workflows set `Review` when a pull request is linked to an Issue, `In progress` when a review requests changes, and `Verify` when the pull request is merged. Keep the Project's `Auto-close issue` workflow disabled.

Also keep the repository setting **Settings → Issues → Auto-close issues with merged linked pull requests** disabled. This is separate from the Project workflow: GitHub can close an Issue when its natively linked PR is merged even if the Project's `Auto-close issue` workflow is off. The repository setting is verified off for this workflow. See [GitHub's setting documentation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/managing-auto-closing-issues).

AI sets selection and implementation states with the repository command:

```sh
scripts/project-status.sh <issue-number> "Ready"
scripts/project-status.sh <issue-number> "In progress"
scripts/project-status.sh <issue-number> "Review"
scripts/project-status.sh <issue-number> "Verify"
scripts/project-status.sh <issue-number> "Done"
```

The command changes only the Status field of exactly one matching Issue item in Project #15. It discovers the field and option IDs from the live Project schema and stops without writing if the Issue item or target status is missing or ambiguous. It never closes an Issue.

## AI operating rules

- When the owner asks AI to choose/brainstorm the next task or names a specific task, identify its Issue. Move that Issue to `Ready` when the owner selects it; ask if the Issue match or scope is ambiguous.
- Move the selected Issue to `In progress` when implementation begins. Keep it there while implementing fixes or filling verification gaps.
- Create/link a PR only when it is ready for review. Keep a draft PR unlinked until it is ready; the native link workflow moves the Issue to `Review`.
- When a review requests changes, continue the work and leave the Issue in `In progress`. After the changes are ready, request review again and use the command above to move the already-linked Issue to `Review`.
- After merge, keep the Issue open in `Verify`. Check every acceptance criterion and report evidence. If one is missing, move it to `In progress` and continue.
- Only explicit owner acceptance permits moving to `Done` and closing the Issue. Passing CI, review approval, or merge is not owner acceptance. Keep both auto-close settings above disabled so a merge leaves the Issue open in `Verify`.
- For blocked work, keep the current status, add the `blocked` label, and record the dependency and next action on the Issue.

## Pull request creation

Before creating a PR, read the owning Issue's labels and milestone. Set PR metadata in the creation command: assign it to `javis-27`, request review from `biendo27`, and copy every Issue label and its milestone. For example:

```sh
gh pr create \
  --assignee javis-27 \
  --reviewer biendo27 \
  --label "<issue-label>" \
  --milestone "<issue-milestone>"
```

Repeat `--label` once per label on the Issue. Link exactly one owning Issue through the PR's native **Development** relationship when the PR is ready for review. Do not use `Fixes`, `Closes`, or `Resolves` in the PR body. These keywords are not the protection against merge closure: both auto-close settings must remain disabled. A plain `Refs #N` mention does not create the native relationship.

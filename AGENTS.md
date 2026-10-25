# Project instructions

## Owner control

- Work only on the owner-selected issue and authorized scope. Do not start the next issue without the owner's selection.
- Ask the owner before changing scope or accepted architecture decisions.
- Obtain explicit owner authorization for final acceptance, issue closure, PR merge, production deployment, and release. Passing checks or merging a PR does not establish acceptance.
- After owner acceptance, check verified Issue criteria, set Project status, and clear stale PR actions per [the GitHub workflow](docs/08-github-project-workflow.md); accepted work must not remain in `Review`.

## Project conventions

- Read the selected issue's acceptance criteria and the relevant documents in the [documentation index](docs/00-index.md) before implementation.
- Follow the [system architecture](docs/02-system-architecture.md) for dependency boundaries and the [code standards](docs/04-code-standards.md) for contracts, testing, and contributions.
- Use the [deployment direction](docs/06-deployment-guide.md) when working on shipping or production operations.

## Issue and PR writing

- Keep Issue and PR text concise: include only the goal, material constraints, completion criteria, and verification evidence. Do not repeat metadata already stored in GitHub fields or include personal identifiers unless essential.
- Write each Issue acceptance criterion as an unchecked checkbox (`- [ ]`) and include only observable outcomes needed to decide completion.
- Follow `.github/pull_request_template.md` for PR descriptions. Keep to its sections and omit copied Issue criteria, delegation or review history, ship metadata, owner-action checklists, identity names, and unrelated detail.

## Verification

- Resolve setup and verification commands from existing scripts, manifests, and workflows; do not invent commands or present planned tooling as available.
- Report the checks actually run, their results, and any verification gaps. Distinguish implemented behavior from design requirements.

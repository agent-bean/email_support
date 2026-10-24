# Project instructions

## Owner control

- Work only on the owner-selected issue and authorized scope. Do not start the next issue without the owner's selection.
- Ask the owner before changing scope or accepted architecture decisions.
- Obtain explicit owner authorization for final acceptance, issue closure, PR merge, production deployment, and release. Passing checks or merging a PR does not establish acceptance.

## Project conventions

- Read the selected issue's acceptance criteria and the relevant documents in the [documentation index](docs/00-index.md) before implementation.
- Follow the [system architecture](docs/02-system-architecture.md) for dependency boundaries and the [code standards](docs/04-code-standards.md) for contracts, testing, and contributions.
- Use the [deployment direction](docs/06-deployment-guide.md) when working on shipping or production operations.

## Verification

- Resolve setup and verification commands from existing scripts, manifests, and workflows; do not invent commands or present planned tooling as available.
- Report the checks actually run, their results, and any verification gaps. Distinguish implemented behavior from design requirements.

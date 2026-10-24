#!/usr/bin/env bash
set -euo pipefail

repository_root="$(git -C "$(dirname -- "${BASH_SOURCE[0]}")/.." rev-parse --show-toplevel)"
cd "$repository_root"

generated_paths=(
  apps/backend/openapi.json
  apps/web/src/shared/api/generated/
)

if [[ -n "$(git status --porcelain --untracked-files=all -- "${generated_paths[@]}")" ]]; then
  printf '%s\n' 'Generated API artifacts are dirty before generation; inspect and preserve them, then run make generate intentionally.' >&2
  git status --short --untracked-files=all -- "${generated_paths[@]}" >&2
  exit 1
fi

make generate

if [[ -n "$(git status --porcelain --untracked-files=all -- "${generated_paths[@]}")" ]]; then
  printf '%s\n' 'Generated API artifacts drift from the committed backend contract.' >&2
  git status --short --untracked-files=all -- "${generated_paths[@]}" >&2
  exit 1
fi

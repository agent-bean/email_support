#!/usr/bin/env bash
set -euo pipefail

readonly owner="agent-bean"
readonly repository="email_support"
readonly project_number=15

usage() {
  cat <<'EOF'
Usage: scripts/project-status.sh <issue-number> <status>

Set only the Status field for one Issue item in agent-bean Project #15.
Allowed statuses: Backlog, Ready, In progress, Review, Verify, Done, Dropped.
The command never closes an Issue.
EOF
}

fail() {
  printf 'project-status: %s\n' "$1" >&2
  exit 1
}

if [[ $# -ne 2 ]]; then
  usage >&2
  exit 2
fi

issue_number="$1"
target_status="$2"

if [[ ! "$issue_number" =~ ^[1-9][0-9]*$ ]]; then
  fail "issue number must be a positive integer"
fi

case "$target_status" in
  Backlog|Ready|"In progress"|Review|Verify|Done|Dropped) ;;
  *) fail "unknown status '$target_status'" ;;
esac

command -v gh >/dev/null 2>&1 || fail "GitHub CLI (gh) is required"
command -v jq >/dev/null 2>&1 || fail "jq is required"

project_query='query($owner:String!,$number:Int!){organization(login:$owner){projectV2(number:$number){id fields(first:100){nodes{... on ProjectV2SingleSelectField{id name options{id name}}}}}}}'
project_json="$(gh api graphql -f query="$project_query" -F owner="$owner" -F number="$project_number")" \
  || fail "could not read Project #$project_number"

project_id="$(jq -er '.data.organization.projectV2.id // empty' <<<"$project_json")" \
  || fail "Project #$project_number was not found in organization '$owner'"

status_fields="$(jq '[.data.organization.projectV2.fields.nodes[] | select(.name == "Status")]' <<<"$project_json")"
status_field_count="$(jq 'length' <<<"$status_fields")"
[[ "$status_field_count" -eq 1 ]] || fail "expected one Status field in Project #$project_number; found $status_field_count"

status_field_id="$(jq -er '.[0].id' <<<"$status_fields")" \
  || fail "could not read the Status field ID"
status_options="$(jq --arg status "$target_status" '[.[0].options[] | select(.name == $status)]' <<<"$status_fields")"
status_option_count="$(jq 'length' <<<"$status_options")"
[[ "$status_option_count" -eq 1 ]] || fail "expected one Project status named '$target_status'; found $status_option_count"
status_option_id="$(jq -er '.[0].id' <<<"$status_options")" \
  || fail "could not read the '$target_status' option ID"

items_json="$(gh project item-list "$project_number" --owner "$owner" --format json --limit 1000)" \
  || fail "could not read Project #$project_number items"
matches="$(jq --argjson number "$issue_number" --arg repository "$owner/$repository" \
  '[.items[] | select(.content.type == "Issue" and .content.repository == $repository and .content.number == $number)]' \
  <<<"$items_json")"
match_count="$(jq 'length' <<<"$matches")"
[[ "$match_count" -eq 1 ]] || fail "expected one Project item for $owner/$repository#$issue_number; found $match_count"

item_id="$(jq -er '.[0].id' <<<"$matches")" \
  || fail "could not read the Project item ID for Issue #$issue_number"
current_status="$(jq -r '.[0].status // empty' <<<"$matches")"

if [[ "$current_status" == "$target_status" ]]; then
  printf 'Issue #%s already has Project status %s.\n' "$issue_number" "$target_status"
  exit 0
fi

gh project item-edit \
  --id "$item_id" \
  --project-id "$project_id" \
  --field-id "$status_field_id" \
  --single-select-option-id "$status_option_id" \
  || fail "could not set Issue #$issue_number to '$target_status'"

printf 'Set Issue #%s Project status to %s.\n' "$issue_number" "$target_status"

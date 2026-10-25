#!/usr/bin/env bash
set -Eeuo pipefail

mode="${1:-}"
if [[ -z "$mode" ]]; then
  printf 'usage: %s {local|ci|up|down} [pytest-path ...]\n' "$0" >&2
  exit 2
fi
shift

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend_root="$repo_root/apps/backend"
compose_file="$repo_root/compose.test.yaml"
project_name="email-support-test"
test_port=55432
service_name=postgres

case "$mode" in
  local|up|down)
    state_root="$repo_root/.test-database"
    service_kind=compose
    ;;
  ci)
    if [[ "${CI:-}" != "true" ]]; then
      printf 'CI database mode requires CI=true\n' >&2
      exit 2
    fi
    ci_password="${EMAIL_SUPPORT_TEST_POSTGRES_PASSWORD:-}"
    ci_container_id="${EMAIL_SUPPORT_TEST_CONTAINER_ID:-}"
    if [[ ! "$ci_password" =~ ^[A-Za-z0-9._-]{24,128}$ ]]; then
      printf 'CI database mode requires a job-scoped test PostgreSQL password\n' >&2
      exit 2
    fi
    if [[ ! "$ci_container_id" =~ ^[a-f0-9]{64}$ ]]; then
      printf 'CI database mode requires the PostgreSQL service container ID\n' >&2
      exit 2
    fi
    runner_temp="${RUNNER_TEMP:-/tmp}"
    state_root="$(mktemp -d "$runner_temp/email-support-database.XXXXXX")"
    service_kind=github-actions
    ;;
  *)
    printf 'unknown database mode: %s\n' "$mode" >&2
    exit 2
    ;;
esac

mkdir -p "$state_root"
if [[ -L "$state_root" ]]; then
  printf 'test database state directory must not be a symlink\n' >&2
  exit 1
fi
if [[ "$(stat -c %u -- "$state_root")" != "$(id -u)" ]]; then
  printf 'test database state directory must be owned by the current user\n' >&2
  exit 1
fi
chmod 700 "$state_root"
export EMAIL_SUPPORT_TEST_UID="$(id -u)"
export EMAIL_SUPPORT_TEST_GID="$(id -g)"
if [[ "$EMAIL_SUPPORT_TEST_UID" == 0 ]]; then
  printf 'test PostgreSQL must run as the owner of its private data directory, not root\n' >&2
  exit 1
fi
export EMAIL_SUPPORT_TEST_DATA_DIR="$state_root/postgres-data-$EMAIL_SUPPORT_TEST_UID"
export EMAIL_SUPPORT_TEST_BACKUP_DIR="$state_root/recovery"
export EMAIL_SUPPORT_TEST_COMPOSE_FILE="$compose_file"
export EMAIL_SUPPORT_TEST_PROJECT_NAME="$project_name"
export EMAIL_SUPPORT_TEST_PORT=55432
export EMAIL_SUPPORT_TEST_SERVICE_KIND="$service_kind"
export EMAIL_SUPPORT_TEST_RUN_ID="$(openssl rand -hex 4)"
mkdir -p "$EMAIL_SUPPORT_TEST_BACKUP_DIR"
if [[ "$mode" != ci ]]; then
  mkdir -p "$EMAIL_SUPPORT_TEST_DATA_DIR"
fi
if [[ ( "$mode" != ci && -L "$EMAIL_SUPPORT_TEST_DATA_DIR" ) || -L "$EMAIL_SUPPORT_TEST_BACKUP_DIR" ]]; then
  printf 'test database storage paths must not be symlinks\n' >&2
  exit 1
fi
if [[ "$(stat -c %u -- "$EMAIL_SUPPORT_TEST_BACKUP_DIR")" != "$EMAIL_SUPPORT_TEST_UID" || \
  ( "$mode" != ci && "$(stat -c %u -- "$EMAIL_SUPPORT_TEST_DATA_DIR")" != "$EMAIL_SUPPORT_TEST_UID" ) ]]; then
  printf 'test database storage paths must be owned by the current user\n' >&2
  exit 1
fi
chmod 700 "$EMAIL_SUPPORT_TEST_BACKUP_DIR"
if [[ "$mode" != ci ]]; then
  chmod 700 "$EMAIL_SUPPORT_TEST_DATA_DIR"
fi

if [[ "$mode" == ci ]]; then
  export EMAIL_SUPPORT_TEST_POSTGRES_PASSWORD="$ci_password"
  export EMAIL_SUPPORT_TEST_CONTAINER_ID="$ci_container_id"
else
  runtime_file="$state_root/runtime.conf"
  if [[ -L "$runtime_file" || ( -e "$runtime_file" && ! -f "$runtime_file" ) ]]; then
    printf 'private test database credentials file is not a regular file\n' >&2
    exit 1
  fi
  if [[ -e "$runtime_file" && "$(stat -c %u -- "$runtime_file")" != "$EMAIL_SUPPORT_TEST_UID" ]]; then
    printf 'private test database credentials file must be owned by the current user\n' >&2
    exit 1
  fi
  if [[ ! -f "$runtime_file" ]]; then
    password="$(openssl rand -hex 32)"
    umask 077
    printf 'EMAIL_SUPPORT_TEST_POSTGRES_PASSWORD=%s\n' "$password" > "$runtime_file"
  fi
  chmod 600 "$runtime_file"
  runtime_contents="$(<"$runtime_file")"
  if [[ ! "$runtime_contents" =~ ^EMAIL_SUPPORT_TEST_POSTGRES_PASSWORD=([a-f0-9]{64})$ ]]; then
    printf 'private test database credentials file has an invalid format\n' >&2
    exit 1
  fi
  export EMAIL_SUPPORT_TEST_POSTGRES_PASSWORD="${BASH_REMATCH[1]}"
  export EMAIL_SUPPORT_TEST_CONTAINER_ID=""
fi
export EMAIL_SUPPORT_TEST_SERVER_IDENTIFIER=""
export EMAIL_SUPPORT_TEST_DATABASE_URL="postgresql+psycopg://email_support_test_admin:${EMAIL_SUPPORT_TEST_POSTGRES_PASSWORD}@127.0.0.1:55432/postgres"

compose=(docker compose --project-name "$project_name" --file "$compose_file")
container_id=""
service_verified=false

verify_service() {
  local candidate_id="$1"
  local server_identifier
  server_identifier="$(cd "$backend_root" && uv run --locked python scripts/test_database.py verify-service \
    --container-id "$candidate_id" \
    --compose-file "$compose_file" \
    --project-name "$project_name" \
    --port 55432 \
    --service-kind "$service_kind")"
  if [[ ! "$server_identifier" =~ ^[0-9]+$ ]]; then
    printf 'test server identity is invalid\n' >&2
    return 1
  fi
  container_id="$candidate_id"
  export EMAIL_SUPPORT_TEST_CONTAINER_ID="$container_id"
  export EMAIL_SUPPORT_TEST_SERVER_IDENTIFIER="$server_identifier"
  service_verified=true
  printf 'Verified owned PostgreSQL test service: container=%s port=127.0.0.1:55432 server=%s\n' \
    "${container_id:0:12}" "$server_identifier"
}

stop_owned_service() {
  if [[ "$service_verified" != true || -z "$container_id" ]]; then
    return 0
  fi
  (cd "$backend_root" && uv run --locked python scripts/test_database.py stop-owned \
    --container-id "$container_id" \
    --compose-file "$compose_file" \
    --project-name "$project_name" \
    --port 55432)
}

start_or_reuse_service() {
  if [[ "$mode" == ci ]]; then
    verify_service "$ci_container_id"
    return
  fi
  docker compose --project-name "$project_name" --file "$compose_file" config --quiet
  local running_id
  running_id="$("${compose[@]}" ps --quiet "$service_name" 2>/dev/null || true)"
  if ss -ltnH 'sport = :55432' | rg -q . && [[ -z "$running_id" ]]; then
    printf '127.0.0.1:55432 is owned by a service outside %s; refusing to start PostgreSQL\n' \
      "$project_name" >&2
    return 1
  fi
  if [[ -z "$running_id" ]]; then
    "${compose[@]}" up --detach --wait --wait-timeout 90 "$service_name"
    running_id="$("${compose[@]}" ps --quiet "$service_name")"
  fi
  if [[ -z "$running_id" ]]; then
    printf 'owned PostgreSQL service did not start\n' >&2
    return 1
  fi
  verify_service "$running_id"
}

finish() {
  local status=$?
  trap - EXIT
  if [[ "$mode" == ci ]]; then
    if [[ "$service_verified" != true ]]; then
      rm -rf -- "$state_root"
    elif [[ "$status" -eq 0 ]]; then
      if (cd "$backend_root" && uv run --locked python scripts/test_database.py finish-success); then
        rm -rf -- "$state_root"
      else
        status=$?
        printf 'CI PostgreSQL service will be disposed with the job; private recovery data retained at %s\n' \
          "$EMAIL_SUPPORT_TEST_BACKUP_DIR" >&2
      fi
    else
      printf 'CI PostgreSQL service will be disposed with the job; private recovery data retained at %s\n' \
        "$EMAIL_SUPPORT_TEST_BACKUP_DIR" >&2
    fi
    exit "$status"
  fi
  if [[ "$service_verified" == true ]]; then
    if [[ "$status" -eq 0 && "$mode" != up && "$mode" != down ]]; then
      if (cd "$backend_root" && uv run --locked python scripts/test_database.py finish-success); then
        "${compose[@]}" down --timeout 15
      else
        status=$?
        stop_owned_service || true
        printf 'PostgreSQL stopped; database state and verified archives retained at %s\n' \
          "$EMAIL_SUPPORT_TEST_BACKUP_DIR" >&2
      fi
    elif [[ "$mode" == down && "$status" -eq 0 ]]; then
      "${compose[@]}" down --timeout 15
    elif [[ "$mode" != up ]]; then
      stop_owned_service || true
      printf 'PostgreSQL stopped; database state and verified archives retained at %s\n' \
        "$EMAIL_SUPPORT_TEST_BACKUP_DIR" >&2
    fi
  fi
  exit "$status"
}

trap finish EXIT
start_or_reuse_service

case "$mode" in
  up)
    printf 'PostgreSQL test service is running on 127.0.0.1:55432 (container %s).\n' \
      "${container_id:0:12}"
    trap - EXIT
    ;;
  down)
    cd "$backend_root"
    uv run --locked python scripts/test_database.py shutdown-cleanup
    ;;
  local|ci)
    cd "$backend_root"
    uv run --locked python scripts/test_database.py recover-owned-targets
    if [[ "$#" -eq 0 ]]; then
      set -- tests/database
    fi
    uv run --locked pytest -q "$@"
    ;;
esac

#!/usr/bin/env bash
set -Eeuo pipefail

readonly PROJECT=email-support-auth-local
readonly ROOT="$(pwd -P)/.local-auth"
readonly CONFIG="$ROOT/owner.conf"
readonly PASSWORD_FILE="$ROOT/database-password"

fail() {
  printf 'local-auth: %s\n' "$1" >&2
  exit 1
}

[[ $# -eq 1 ]] || fail 'usage: scripts/local-auth.sh {up|migrate|down|smoke|resolve-revoke}'
case "$1" in up|migrate|down|smoke|resolve-revoke) ACTION=$1 ;; *) fail 'usage: scripts/local-auth.sh {up|migrate|down|smoke|resolve-revoke}' ;; esac

[[ ! -L "$ROOT" ]] || fail 'runtime directory must not be a symbolic link'
mkdir -p -m 700 "$ROOT"
chmod 700 "$ROOT"
[[ ! -L "$ROOT" && -d "$ROOT" ]] || fail 'runtime directory must be a real directory'
[[ "$(stat -c '%u' "$ROOT")" == "$(id -u)" ]] || fail 'runtime directory is not owned by the current user'
[[ -f "$CONFIG" && ! -L "$CONFIG" ]] || fail 'create .local-auth/owner.conf with the required private Google settings'
[[ "$(stat -c '%a' "$CONFIG")" == 600 ]] || fail 'owner.conf must have mode 0600'
[[ "$(stat -c '%u' "$CONFIG")" == "$(id -u)" ]] || fail 'owner.conf must be owned by the current user'

declare -A settings=()
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" == \#* ]] && continue
  [[ "$line" == *=* ]] || fail 'owner.conf contains a malformed line'
  key=${line%%=*}
  value=${line#*=}
  case "$key" in
    EMAIL_SUPPORT_OWNER_SUB|EMAIL_SUPPORT_GOOGLE_CLIENT_ID|EMAIL_SUPPORT_GOOGLE_CLIENT_SECRET|EMAIL_SUPPORT_GOOGLE_CALLBACK_URI|EMAIL_SUPPORT_WEB_ORIGIN|EMAIL_SUPPORT_GOOGLE_TOKEN_ENCRYPTION_KEY) ;;
    *) fail 'owner.conf contains an unsupported key' ;;
  esac
  [[ -n "$value" && "$value" != *$'\r'* ]] || fail 'owner.conf contains an empty or malformed value'
  [[ -z "${settings[$key]+present}" ]] || fail 'owner.conf contains a duplicate key'
  settings[$key]=$value
done < "$CONFIG"
for key in EMAIL_SUPPORT_OWNER_SUB EMAIL_SUPPORT_GOOGLE_CLIENT_ID EMAIL_SUPPORT_GOOGLE_CLIENT_SECRET EMAIL_SUPPORT_GOOGLE_CALLBACK_URI EMAIL_SUPPORT_WEB_ORIGIN; do
  [[ -n "${settings[$key]:-}" ]] || fail 'owner.conf is missing a required value'
  export "$key=${settings[$key]}"
done
if [[ -n "${settings[EMAIL_SUPPORT_GOOGLE_TOKEN_ENCRYPTION_KEY]:-}" ]]; then
  export EMAIL_SUPPORT_GOOGLE_TOKEN_ENCRYPTION_KEY="${settings[EMAIL_SUPPORT_GOOGLE_TOKEN_ENCRYPTION_KEY]}"
fi
if [[ "$ACTION" == smoke && -z "${settings[EMAIL_SUPPORT_GOOGLE_TOKEN_ENCRYPTION_KEY]:-}" ]]; then
  fail 'Google token encryption key is required for smoke; configure it in owner.conf'
fi

[[ ! -L "$PASSWORD_FILE" ]] || fail 'database password path must not be a symbolic link'
if [[ ! -e "$PASSWORD_FILE" ]]; then
  (umask 077; openssl rand -hex 32 > "$PASSWORD_FILE") || fail 'could not create the private database password'
  chmod 600 "$PASSWORD_FILE"
fi
[[ -f "$PASSWORD_FILE" && ! -L "$PASSWORD_FILE" && "$(stat -c '%a' "$PASSWORD_FILE")" == 600 ]] || fail 'database password file must be a private regular file with mode 0600'
[[ "$(stat -c '%u' "$PASSWORD_FILE")" == "$(id -u)" ]] || fail 'database password file must be owned by the current user'
LOCAL_AUTH_DB_PASSWORD=$(<"$PASSWORD_FILE")
[[ "$LOCAL_AUTH_DB_PASSWORD" =~ ^[a-f0-9]{64}$ ]] || fail 'database password file is malformed'
[[ ! -L "$ROOT/postgres-data" && ! -L "$ROOT/backups" ]] || fail 'runtime data and backup paths must not be symbolic links'
LOCAL_AUTH_ROOT=$ROOT
LOCAL_AUTH_UID=$(id -u)
LOCAL_AUTH_GID=$(id -g)
EMAIL_SUPPORT_DATABASE_URL="postgresql+psycopg://email_support_auth:${LOCAL_AUTH_DB_PASSWORD}@auth-postgres:5432/email_support_auth"
export LOCAL_AUTH_DB_PASSWORD LOCAL_AUTH_ROOT LOCAL_AUTH_UID LOCAL_AUTH_GID EMAIL_SUPPORT_DATABASE_URL
mkdir -p -m 700 "$ROOT/postgres-data" "$ROOT/backups"
chmod 700 "$ROOT/postgres-data" "$ROOT/backups"
[[ "$(stat -c '%u' "$ROOT/postgres-data")" == "$(id -u)" && "$(stat -c '%u' "$ROOT/backups")" == "$(id -u)" ]] || fail 'runtime data and backup directories must be owned by the current user'

compose() {
  docker compose --project-name "$PROJECT" --profile auth --env-file "$CONFIG" -f compose.yaml -f compose.auth.yaml "$@"
}

check_owned_postgres() {
  local id project service marker mount
  id=$(compose ps --status running --quiet auth-postgres)
  [[ -n "$id" && "$id" != *$'\n'* ]] || fail 'the owned auth PostgreSQL service is not running'
  project=$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$id")
  service=$(docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "$id")
  marker=$(docker inspect --format '{{index .Config.Labels "com.email_support.local_auth"}}' "$id")
  mount=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql"}}{{.Source}}{{end}}{{end}}' "$id")
  [[ "$project" == "$PROJECT" && "$service" == auth-postgres && "$marker" == true && "$mount" == "$ROOT/postgres-data" ]] || fail 'database container identity does not match the private auth runtime'
}

db_query() {
  compose exec --no-TTY auth-postgres sh -ec 'PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 -U email_support_auth -d email_support_auth -Atqc "$1"' sh "$1"
}

db_owner_query() {
  local query=$1 operation_id=${2:-}
  compose exec --no-TTY \
    --env "LOCAL_AUTH_OWNER_SUB=$EMAIL_SUPPORT_OWNER_SUB" \
    --env "LOCAL_AUTH_REVOKE_OPERATION_ID=$operation_id" \
    auth-postgres sh -ec 'PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 -v owner_sub="$LOCAL_AUTH_OWNER_SUB" -v operation_id="$LOCAL_AUTH_REVOKE_OPERATION_ID" -U email_support_auth -d email_support_auth -Atqc "$1"' sh "$query"
}

run_alembic() {
  compose run --rm --no-deps --env EMAIL_SUPPORT_ALEMBIC_DATABASE_URL api /app/.venv/bin/alembic -c /app/alembic.ini "$@"
}

backup_database() {
  local archive="$ROOT/backups/$(date -u +%Y%m%dT%H%M%SZ)-$$.dump"
  (umask 077; compose exec --no-TTY auth-postgres sh -ec 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump --format=custom --username=email_support_auth --dbname=email_support_auth' > "$archive") || fail "database backup failed; partial archive retained at $archive"
  chmod 600 "$archive"
  compose exec --no-TTY auth-postgres pg_restore --list < "$archive" >/dev/null || fail "database backup validation failed; archive retained at $archive"
  printf '%s\n' "$archive"
}

case "$ACTION" in
  up)
    for port in 5173 8000; do
      if ss -ltnH "sport = :$port" | grep -q .; then
        mapfile -t published < <(docker ps --quiet --filter "publish=$port")
        [[ ${#published[@]} -gt 0 ]] || fail "port $port is occupied; inspect its owner before starting the authenticated runtime"
        for id in "${published[@]}"; do
          project=$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$id")
          [[ "$project" == "$PROJECT" ]] || fail "port $port is owned outside the authenticated runtime"
        done
      fi
    done
    compose up --detach --wait --wait-timeout 90 auth-postgres
    check_owned_postgres
    "$0" migrate
    compose up --detach --build --wait --wait-timeout 90 api web
    ;;
  migrate)
    check_owned_postgres
    target=$(run_alembic heads | awk '$1 ~ /^[0-9a-f]+$/ {print $1}')
    [[ -n "$target" && "$target" != *$'\n'* ]] || fail 'could not determine one Alembic head'
    has_version=$(db_query "SELECT to_regclass('public.alembic_version') IS NOT NULL") || fail 'could not inspect the migration revision'
    if [[ "$has_version" == f ]]; then
      table_count=$(db_query "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'") || fail 'could not verify the initial database state'
      [[ "$table_count" == 0 ]] || fail 'database has application tables but no Alembic revision; refusing migration'
      current=empty
    elif [[ "$has_version" == t ]]; then
      current=$(db_query 'SELECT version_num FROM alembic_version') || fail 'could not read the migration revision'
      [[ -n "$current" && "$current" != *$'\n'* ]] || fail 'database has an unknown or multiple migration revisions'
    else
      fail 'migration revision query returned an invalid result'
    fi
    if [[ "$current" == "$target" ]]; then
      exit 0
    fi
    backup_database >/dev/null
    EMAIL_SUPPORT_ALEMBIC_DATABASE_URL=$EMAIL_SUPPORT_DATABASE_URL run_alembic upgrade head
    ;;
  down)
    existing=$(compose ps --all --quiet)
    if [[ -n "$existing" ]]; then
      while IFS= read -r id; do
        [[ -z "$id" ]] && continue
        project=$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$id")
        [[ "$project" == "$PROJECT" ]] || fail 'found a container outside the owned auth project'
      done <<< "$existing"
    fi
    compose down --remove-orphans
    ;;
  smoke)
    api_id=$(compose ps --status running --quiet api)
    [[ -n "$api_id" && "$api_id" != *$'\n'* ]] || fail 'the owned auth API service is not running'
    project=$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$api_id")
    service=$(docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "$api_id")
    [[ "$project" == "$PROJECT" && "$service" == api ]] || fail 'API container identity does not match the private auth runtime'
    compose exec --no-TTY api /app/.venv/bin/python /app/scripts/live-google-smoke.py
    ;;
  resolve-revoke)
    check_owned_postgres
    api_id=$(compose ps --status running --quiet api)
    if [[ -n "$api_id" ]]; then
      compose stop --timeout 10 api
    fi
    api_id=$(compose ps --status running --quiet api)
    [[ -z "$api_id" ]] || fail 'could not stop the owner API before revoke recovery'
    operation_id=$(db_owner_query "SELECT revoke_operation_id FROM google_connections WHERE owner_sub = :'owner_sub' AND revoke_state IN ('in_progress', 'unknown') AND revoke_outcome = 'unknown' AND status = 'disconnected' AND encrypted_token_bundle IS NULL") || fail 'could not inspect the unresolved Google revoke'
    [[ "$operation_id" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]] || fail 'no single purged unresolved Google revoke was found'
    read -r -p 'Verify this app grant is removed in Google Account permissions; type REMOVED to confirm: ' confirmation
    [[ "$confirmation" == REMOVED ]] || fail 'operator confirmation is required'
    read -r -p "Enter the exact revoke operation ID ($operation_id): " supplied_operation_id
    [[ "$supplied_operation_id" == "$operation_id" ]] || fail 'revoke operation ID did not match'
    resolved_id=$(db_owner_query "UPDATE google_connections SET revoke_state = 'resolved', revoke_outcome = 'confirmed', revoke_recorded_at = now(), last_error = NULL, updated_at = now() WHERE owner_sub = :'owner_sub' AND revoke_operation_id = :'operation_id' AND revoke_state IN ('in_progress', 'unknown') AND revoke_outcome = 'unknown' AND status = 'disconnected' AND encrypted_token_bundle IS NULL RETURNING revoke_operation_id" "$operation_id") || fail 'guarded Google revoke recovery transaction failed'
    [[ "$resolved_id" == "$operation_id" ]] || fail 'the unresolved revoke changed; no marker was cleared'
    printf 'Google revoke marker resolved for the confirmed operation. Restart the owner runtime with scripts/local-auth.sh up.\n'
    ;;
esac

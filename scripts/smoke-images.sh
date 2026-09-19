#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# == 3 ]] || { printf 'Usage: smoke-images.sh BACKEND_IMAGE FRONTEND_IMAGE VERSION\n' >&2; exit 1; }
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
unset COMPOSE_FILE COMPOSE_PROJECT_NAME COMPOSE_PROFILES COMPOSE_ENV_FILES COMPOSE_PATH_SEPARATOR
set -a
. scripts/ci.env
set +a
export APP_IMAGE=$1 FRONTEND_IMAGE=$2
expected_version=$3
stage=$(mktemp -d /tmp/uptime-ci-XXXXXXXX)
project=$(basename "$stage" | tr '[:upper:]' '[:lower:]')
printf 'services:\n  frontend:\n    ports: !override []\n' > "$stage/compose.yml"
compose() {
  docker compose --project-name "$project" --env-file scripts/ci.env \
    -f compose.yml -f "$stage/compose.yml" "$@"
}
cleanup() {
  status=$?
  trap - EXIT
  if ((status != 0)); then compose logs --no-color --tail=80 || true; fi
  compose down --volumes --remove-orphans >/dev/null || true
  rm -rf -- "$stage"
  exit "$status"
}
trap cleanup EXIT
compose up -d --wait --wait-timeout 120 postgres
compose run --rm --no-deps migrate
compose up -d --no-deps --wait --wait-timeout 120 api scheduler notification-worker frontend
for ((attempt=0; attempt<30; attempt++)); do
  if compose exec -T frontend wget -q -T 2 -O - http://127.0.0.1/backend/health > "$stage/health.json"; then break; fi
  sleep 1
done
compose exec -T frontend wget -q -T 5 -O - http://127.0.0.1/ > "$stage/index.html"
compose exec -T frontend wget -q -T 5 -O - http://127.0.0.1/backend/openapi.json > "$stage/openapi.json"
node - "$stage" "$expected_version" <<'JS'
const fs = require('node:fs');
const assert = require('node:assert/strict');
const [stage, expected] = process.argv.slice(2);
assert.equal(JSON.parse(fs.readFileSync(`${stage}/health.json`)).status, 'ok');
assert.equal(JSON.parse(fs.readFileSync(`${stage}/openapi.json`)).info.version, expected);
assert.match(fs.readFileSync(`${stage}/index.html`, 'utf8'), /<html/i);
JS
compose exec -T postgres pg_dump -U uptime uptime_test > "$stage/database.sql"
[[ -s "$stage/database.sql" ]]
printf 'Image smoke checks passed for %s.\n' "$expected_version"

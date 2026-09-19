#!/usr/bin/env bash
set -Eeuo pipefail

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
VERSION=${1:-patch}
[[ $# -le 1 && "$VERSION" =~ ^(patch|minor|major|(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*))$ ]] || fail 'Usage: make release VERSION=patch|minor|major|X.Y.Z'
for executable in git gh; do
  command -v "$executable" >/dev/null || fail "Install $executable first."
done
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
[[ "$(git branch --show-current)" == main ]] || fail 'Run releases from main.'
[[ -z "$(git status --porcelain)" ]] || fail 'Commit your changes first; the release command requires a clean working tree.'
REPOSITORY=nightingale-develop/uptime-platform
origin=$(git remote get-url --push origin)
case "$origin" in
  "git@github.com:$REPOSITORY.git"|"https://github.com/$REPOSITORY.git"|"https://github.com/$REPOSITORY") ;;
  *) fail "origin must point to $REPOSITORY." ;;
esac
gh auth status --hostname github.com >/dev/null
git push origin main
commit=$(git rev-parse HEAD)
request_id="$(date -u +%Y%m%dT%H%M%S)-$$-$RANDOM"
gh workflow run release.yml --repo "$REPOSITORY" --ref main \
  -f "version=$VERSION" -f "expected_sha=$commit" -f "request_id=$request_id"
run_id=
for ((attempt=0; attempt<30; attempt++)); do
  run_id=$(gh run list --repo "$REPOSITORY" --workflow release.yml --event workflow_dispatch \
    --limit 50 --json databaseId,displayTitle \
    --jq ".[] | select(.displayTitle == \"Release $request_id\") | .databaseId")
  [[ -z "$run_id" ]] || break
  sleep 2
done
[[ -n "$run_id" ]] || fail "Workflow dispatched. Find Release $request_id in GitHub Actions."
printf 'Release run: https://github.com/%s/actions/runs/%s\n' "$REPOSITORY" "$run_id"
gh run watch "$run_id" --repo "$REPOSITORY" --exit-status
git pull --ff-only origin main
git fetch origin --tags '+refs/tags/latest:refs/tags/latest'

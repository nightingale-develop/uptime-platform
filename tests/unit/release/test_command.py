import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def release_command(tmp_path):
    log = tmp_path / "commands.log"
    git = tmp_path / "git"
    git.write_text("""#!/bin/bash
printf 'git %s\n' "$*" >> "$RELEASE_TEST_LOG"
case "$*" in
  'branch --show-current') printf '%s\n' "${TEST_BRANCH:-main}" ;;
  'status --porcelain') printf '%s' "${TEST_DIRTY:-}" ;;
  'remote get-url --push origin') printf '%s\n' 'git@github.com:nightingale-develop/uptime-platform.git' ;;
  'rev-parse HEAD') printf '%040d\n' 1 ;;
  'push origin main') exit "${TEST_PUSH_STATUS:-0}" ;;
  'pull --ff-only origin main'|'fetch origin --tags +refs/tags/latest:refs/tags/latest') ;;
  *) exit 98 ;;
esac
""")
    gh = tmp_path / "gh"
    gh.write_text("""#!/bin/bash
printf 'gh %s\n' "$*" >> "$RELEASE_TEST_LOG"
case "$1 $2" in
  'auth status') ;;
  'workflow run') exit "${TEST_DISPATCH_STATUS:-0}" ;;
  'run list') printf '123\n' ;;
  'run watch') exit "${TEST_WATCH_STATUS:-0}" ;;
  *) exit 99 ;;
esac
""")
    for executable in (git, gh):
        executable.chmod(0o755)

    def run(**overrides):
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/release.sh"), "patch"],
            env={
                **os.environ,
                "PATH": f"{tmp_path}:{os.environ['PATH']}",
                "RELEASE_TEST_LOG": str(log),
                **overrides,
            },
            capture_output=True,
            text=True,
            check=False,
        )
        return result, log.read_text()

    return run


def test_release_pushes_dispatches_waits_then_syncs(release_command):
    result, log = release_command()
    assert result.returncode == 0, result.stderr
    assert "-f version=patch -f expected_sha=" + "0" * 39 + "1" in log
    commands = ["git push", "gh workflow run", "gh run watch", "git pull", "git fetch"]
    assert [log.index(command) for command in commands] == sorted(
        log.index(command) for command in commands
    )
    assert "/actions/runs/123" in result.stdout


@pytest.mark.parametrize(
    ("overrides", "absent"),
    [
        ({"TEST_BRANCH": "feature"}, "git push"),
        ({"TEST_DIRTY": " M README.md"}, "git push"),
        ({"TEST_PUSH_STATUS": "1"}, "gh workflow run"),
        ({"TEST_DISPATCH_STATUS": "1"}, "gh run watch"),
        ({"TEST_WATCH_STATUS": "1"}, "git pull"),
    ],
)
def test_release_stops_on_failure(release_command, overrides, absent):
    result, log = release_command(**overrides)
    assert result.returncode != 0
    assert absent not in log

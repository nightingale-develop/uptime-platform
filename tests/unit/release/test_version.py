import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "release_version", ROOT / "scripts/version.py"
)
version = importlib.util.module_from_spec(spec)
spec.loader.exec_module(version)


@pytest.fixture
def checkout(tmp_path):
    files = [
        "pyproject.toml",
        "uv.lock",
        "src/uptime_platform/main.py",
        "Dockerfile",
        "frontend/Dockerfile",
        "frontend/package.json",
        "frontend/package-lock.json",
        "install.sh",
        "README.md",
    ]
    for filename in files:
        target = tmp_path / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / filename, target)
    return tmp_path


@pytest.mark.parametrize(
    ("requested", "expected"),
    [("patch", "1.3.2"), ("minor", "1.4.0"), ("major", "2.0.0"), ("1.5.7", "1.5.7")],
)
def test_next_version(requested, expected):
    assert version.next_version("1.3.1", requested) == expected


@pytest.mark.parametrize(
    "requested",
    ["1.3.1", "1.3.0", "latest", "v1.4.0", "1.4.0-rc1", "01.4.0", "1.4.0\n"],
)
def test_invalid_or_nonincreasing_version_is_rejected(requested):
    with pytest.raises(ValueError):
        version.next_version("1.3.1", requested)


def test_bump_keeps_dependency_versions_and_checks_all_metadata(checkout):
    installer = (checkout / "install.sh").read_bytes()
    before = json.loads((checkout / "frontend/package-lock.json").read_text())
    old_version = version.update_version(checkout)
    target = version.next_version(old_version, "patch")
    assert version.update_version(checkout, "patch") == target
    assert version.update_version(checkout) == target
    assert (checkout / "install.sh").read_bytes() == installer
    assert b"RELEASE_VERSION=latest\n" in installer
    after = json.loads((checkout / "frontend/package-lock.json").read_text())
    assert after["packages"][""]["version"] == target
    assert {k: v for k, v in before["packages"].items() if k} == {
        k: v for k, v in after["packages"].items() if k
    }


def test_metadata_mismatch_does_not_partially_write(checkout):
    path = checkout / "frontend/package.json"
    data = json.loads(path.read_text())
    data["version"] = "0.0.0"
    path.write_text(json.dumps(data))
    before = {p: p.read_bytes() for p in checkout.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="mismatch"):
        version.update_version(checkout, "patch")
    assert before == {p: p.read_bytes() for p in before}


@pytest.mark.parametrize("missing", ["Dockerfile", "frontend/Dockerfile"])
def test_missing_marker_does_not_partially_write(checkout, missing):
    (checkout / missing).write_text("marker removed\n")
    before = (checkout / "pyproject.toml").read_bytes()
    with pytest.raises(ValueError, match="Expected one version"):
        version.update_version(checkout, "patch")
    assert (checkout / "pyproject.toml").read_bytes() == before


def test_read_only_check_does_not_write(checkout):
    before = {p: p.read_bytes() for p in checkout.rglob("*") if p.is_file()}
    version.update_version(checkout)
    assert before == {p: p.read_bytes() for p in before}


@pytest.mark.parametrize(
    "requested", ["latest", "1.2.3; touch /tmp/invalid", "$(exit 0)"]
)
def test_release_command_rejects_invalid_input_before_git(requested):
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/release.sh"), requested],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Usage:" in result.stderr

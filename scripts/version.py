import argparse
import json
import re
import tomllib
from pathlib import Path

VERSION_PATTERN = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"


def parse_version(value: str) -> tuple[int, ...]:
    if not re.fullmatch(VERSION_PATTERN, value):
        raise ValueError(f"Invalid stable version: {value}")
    return tuple(map(int, value.split(".")))


def next_version(current: str, requested: str) -> str:
    major, minor, patch = parse_version(current)
    increments = {
        "patch": f"{major}.{minor}.{patch + 1}",
        "minor": f"{major}.{minor + 1}.0",
        "major": f"{major + 1}.0.0",
    }
    target = increments.get(requested, requested)
    if parse_version(target) <= parse_version(current):
        raise ValueError(f"Version {target} must be newer than {current}")
    return target


def version_files(root: Path, current: str, target: str) -> dict[Path, str]:
    patterns = {
        "pyproject.toml": r'(?m)^(version = ")([^"\n]+)(")$',
        "uv.lock": r'(\[\[package\]\]\nname = "uptime-platform"\nversion = ")([^"\n]+)(")',
        "src/uptime_platform/main.py": r'(?m)^(    version=")([^"\n]+)(",)$',
        "Dockerfile": r'(?m)^(LABEL org.opencontainers.image.version=")([^"\n]+)(")$',
        "frontend/Dockerfile": r'(?m)^(LABEL org.opencontainers.image.version=")([^"\n]+)(")$',
        "README.md": r"(badge/version-)([^/\n]+?)(-blue\))",
    }
    result = {}
    for filename, pattern in patterns.items():
        path = root / filename
        text = path.read_text()
        matches = list(re.finditer(pattern, text))
        if len(matches) != 1 or matches[0][2] != current:
            raise ValueError(f"Expected one version {current} in {filename}")
        result[path] = re.sub(pattern, lambda m: m[1] + target + m[3], text)
    for filename in ("frontend/package.json", "frontend/package-lock.json"):
        path = root / filename
        data = json.loads(path.read_text())
        if data["version"] != current:
            raise ValueError(f"Version mismatch in {filename}")
        data["version"] = target
        if "packages" in data:
            if data["packages"][""]["version"] != current:
                raise ValueError(f"Root package version mismatch in {filename}")
            data["packages"][""]["version"] = target
        result[path] = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return result


def update_version(root: Path, requested: str | None = None) -> str:
    current = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    parse_version(current)
    target = next_version(current, requested) if requested else current
    replacements = version_files(root, current, target)
    if requested:
        for path, content in replacements.items():
            path.write_text(content)
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("version", nargs="?", help="patch, minor, major or X.Y.Z")
    args = parser.parse_args()
    try:
        print(update_version(Path(__file__).resolve().parents[1], args.version))
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f"Version check failed: {error}\n")


if __name__ == "__main__":
    main()

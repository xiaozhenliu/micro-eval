#!/usr/bin/env python3
"""Synchronize current release version surfaces for micro-eval."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def write_text_if_changed(path: Path, text: str) -> None:
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old != text:
        path.write_text(text, encoding="utf-8")


def replace_current_version_line(text: str, version: str) -> str:
    text = re.sub(r"Current version: `[^`]+`", f"Current version: `{version}`", text)
    return re.sub(
        r"\[!\[Version: [^]]+\]\(https://img\.shields\.io/badge/version-[^-]+-6f42c1\)\]\(VERSION\)",
        f"[![Version: {version}](https://img.shields.io/badge/version-{version}-6f42c1)](VERSION)",
        text,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Target SemVer release version, e.g. 0.1.4")
    args = parser.parse_args()
    version = args.version.strip()
    if not VERSION_RE.match(version):
        raise SystemExit(f"Invalid release version: {version}")

    write_text_if_changed(ROOT / "VERSION", f"{version}\n")

    init_path = ROOT / "src" / "micro_eval" / "__init__.py"
    init_text = init_path.read_text(encoding="utf-8")
    init_text = re.sub(r'__version__ = "[^"]+"', f'__version__ = "{version}"', init_text)
    write_text_if_changed(init_path, init_text)

    readme_path = ROOT / "README.md"
    write_text_if_changed(
        readme_path,
        replace_current_version_line(readme_path.read_text(encoding="utf-8"), version),
    )

    package_json_path = ROOT / "ui" / "package.json"
    package_json = json.loads(package_json_path.read_text(encoding="utf-8"))
    package_json["version"] = version
    write_text_if_changed(package_json_path, json.dumps(package_json, indent=2) + "\n")

    package_lock_path = ROOT / "ui" / "package-lock.json"
    package_lock = json.loads(package_lock_path.read_text(encoding="utf-8"))
    package_lock["version"] = version
    package_lock.setdefault("packages", {}).setdefault("", {})["version"] = version
    write_text_if_changed(package_lock_path, json.dumps(package_lock, indent=2) + "\n")

    fixture_path = ROOT / "ui" / "src" / "lib" / "fixtures" / "canonical-run-p0.json"
    if fixture_path.exists():
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        if "replay_canonical" in fixture:
            fixture["replay_canonical"]["tool_version"] = version
            write_text_if_changed(fixture_path, json.dumps(fixture, indent=2) + "\n")

    print(f"Synced current version surfaces to {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

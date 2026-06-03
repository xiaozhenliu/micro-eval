#!/usr/bin/env python3
"""Check release version surfaces for micro-eval."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

def find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").exists() and (candidate / "VERSION").exists():
            return candidate
    raise RuntimeError("Could not locate micro-eval repository root")


ROOT = find_repo_root()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(read_text(path))


def fail(message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"status": "fail", "message": message, "details": details or {}}


def ok(message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"status": "pass", "message": message, "details": details or {}}


def pyproject_uses_version_file(pyproject: str) -> bool:
    return (
        'dynamic = ["version"]' in pyproject
        and '[tool.hatch.version]' in pyproject
        and 'path = "VERSION"' in pyproject
    )


def static_pyproject_version(pyproject: str) -> str | None:
    match = re.search(r'^version = "([^"]+)"$', pyproject, flags=re.MULTILINE)
    return match.group(1) if match else None


def wheel_metadata_version(path: Path) -> str | None:
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.endswith(".dist-info/METADATA"):
                metadata = archive.read(name).decode("utf-8")
                match = re.search(r"^Version: (.+)$", metadata, flags=re.MULTILINE)
                return match.group(1) if match else None
    return None


def sdist_metadata_version(path: Path) -> str | None:
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            if member.name.endswith("/PKG-INFO"):
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                metadata = extracted.read().decode("utf-8")
                match = re.search(r"^Version: (.+)$", metadata, flags=re.MULTILINE)
                return match.group(1) if match else None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Expected release version. Defaults to VERSION file.")
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    args = parser.parse_args()

    expected = args.version or read_text(ROOT / "VERSION").strip()
    checks: list[dict[str, Any]] = []

    version_file = read_text(ROOT / "VERSION").strip()
    checks.append(ok("VERSION matches", {"value": version_file}) if version_file == expected else fail("VERSION mismatch", {"actual": version_file, "expected": expected}))

    pyproject = read_text(ROOT / "pyproject.toml")
    static_version = static_pyproject_version(pyproject)
    if pyproject_uses_version_file(pyproject):
        checks.append(ok("pyproject uses Hatch dynamic VERSION source"))
    elif static_version == expected:
        checks.append(ok("pyproject static version matches", {"value": static_version}))
    else:
        checks.append(fail("pyproject version source mismatch", {"static_version": static_version, "expected": expected}))

    init_py = read_text(ROOT / "src" / "micro_eval" / "__init__.py")
    checks.append(ok("Python __version__ matches") if f'__version__ = "{expected}"' in init_py else fail("Python __version__ mismatch"))

    planner = read_text(ROOT / "src" / "micro_eval" / "config" / "planner.py")
    checks.append(ok("ReplayCanonical uses runtime __version__") if "tool_version=__version__" in planner else fail("ReplayCanonical tool_version is not runtime-driven"))

    readme = read_text(ROOT / "README.md")
    checks.append(ok("README current version matches") if f"Current version: `{expected}`" in readme else fail("README current version mismatch"))

    package_json = load_json(ROOT / "ui" / "package.json")
    checks.append(ok("ui/package.json version matches") if package_json.get("version") == expected else fail("ui/package.json version mismatch", {"actual": package_json.get("version")}))

    package_lock = load_json(ROOT / "ui" / "package-lock.json")
    lock_root_version = package_lock.get("version")
    lock_package_version = package_lock.get("packages", {}).get("", {}).get("version")
    checks.append(ok("ui/package-lock root versions match") if lock_root_version == expected and lock_package_version == expected else fail("ui/package-lock root version mismatch", {"root": lock_root_version, "package": lock_package_version}))

    fixture_path = ROOT / "ui" / "src" / "lib" / "fixtures" / "canonical-run-p0.json"
    if fixture_path.exists():
        fixture = load_json(fixture_path)
        tool_version = fixture.get("replay_canonical", {}).get("tool_version")
        checks.append(ok("contract fixture tool_version matches") if tool_version == expected else fail("contract fixture tool_version mismatch", {"actual": tool_version}))

    changelog = read_text(ROOT / "CHANGELOG.md")
    checks.append(ok("CHANGELOG contains target heading") if re.search(rf"^## {re.escape(expected)} - \d{{4}}-\d{{2}}-\d{{2}}$", changelog, re.MULTILINE) else fail("CHANGELOG target heading missing"))

    dist_dir = ROOT / "dist"
    if dist_dir.exists():
        wheels = sorted(dist_dir.glob(f"micro_eval-{expected}-*.whl"))
        sdists = sorted(dist_dir.glob(f"micro_eval-{expected}.tar.gz"))
        checks.append(ok("dist wheel name matches") if wheels else fail("dist wheel for expected version missing"))
        checks.append(ok("dist sdist name matches") if sdists else fail("dist sdist for expected version missing"))
        for wheel in wheels:
            metadata_version = wheel_metadata_version(wheel)
            checks.append(ok("wheel metadata version matches", {"file": wheel.name}) if metadata_version == expected else fail("wheel metadata version mismatch", {"file": wheel.name, "actual": metadata_version}))
        for sdist in sdists:
            metadata_version = sdist_metadata_version(sdist)
            checks.append(ok("sdist metadata version matches", {"file": sdist.name}) if metadata_version == expected else fail("sdist metadata version mismatch", {"file": sdist.name, "actual": metadata_version}))

    failures = [check for check in checks if check["status"] != "pass"]
    result = {"expected_version": expected, "status": "fail" if failures else "pass", "checks": checks}

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for check in checks:
            marker = "PASS" if check["status"] == "pass" else "FAIL"
            print(f"[{marker}] {check['message']}")
            if check.get("details"):
                print(f"        {json.dumps(check['details'], sort_keys=True)}")
        print(f"version consistency: {result['status']}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

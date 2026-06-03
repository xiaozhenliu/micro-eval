#!/usr/bin/env python3
"""Generate release dependency inventory for micro-eval."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TIMEOUT_S = 8
MAX_OUTPUT_CHARS = 1200


def sanitize_tool_output(value: str) -> str:
    home = str(Path.home())
    if home and home != "/":
        value = re.sub(re.escape(home) + r"(?:/[^\s:]*)?", "[LOCAL_PATH]", value)
    value = re.sub(r"/Users/[^\s:]+(?:/[^\s:]*)?", "[LOCAL_PATH]", value)
    value = re.sub(r"/home/[^\s:]+(?:/[^\s:]*)?", "[LOCAL_PATH]", value)
    return value[:MAX_OUTPUT_CHARS]


@dataclass(frozen=True)
class ToolCheck:
    name: str
    executable: str
    argv: list[str]


def run_tool(argv: list[str], *, timeout_s: int = DEFAULT_TIMEOUT_S) -> dict[str, Any]:
    executable = shutil.which(argv[0])
    if executable is None:
        return {"available": False, "executable": None, "exit_code": None, "stdout": "", "stderr": "not found"}
    try:
        result = subprocess.run(
            argv,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"available": True, "executable": Path(executable).name, "exit_code": 124, "stdout": "", "stderr": f"timed out after {timeout_s}s"}
    return {
        "available": True,
        "executable": Path(executable).name,
        "exit_code": result.returncode,
        "stdout": sanitize_tool_output(result.stdout.strip()),
        "stderr": sanitize_tool_output(result.stderr.strip()),
    }


def load_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_lock_packages(lock_data: dict[str, Any]) -> list[dict[str, str]]:
    packages = []
    for package in lock_data.get("package", []):
        name = str(package.get("name", ""))
        version = str(package.get("version", ""))
        if name and version:
            packages.append({"name": name, "version": version})
    return sorted(packages, key=lambda item: item["name"])


def normalize_package_lock_packages(lock_data: dict[str, Any]) -> list[dict[str, str]]:
    packages = []
    for path, package in lock_data.get("packages", {}).items():
        if path == "":
            continue
        name = path.removeprefix("node_modules/")
        version = str(package.get("version", ""))
        if name and version:
            packages.append({"name": name, "version": version})
    return sorted(packages, key=lambda item: item["name"])


def markdown_table(rows: list[dict[str, str]], columns: tuple[str, str], *, limit: int | None = None) -> str:
    visible = rows if limit is None else rows[:limit]
    header = f"| {columns[0]} | {columns[1]} |\n| --- | --- |"
    body = "\n".join(f"| `{row[columns[0]]}` | `{row[columns[1]]}` |" for row in visible)
    suffix = ""
    if limit is not None and len(rows) > limit:
        suffix = f"\n\n_... {len(rows) - limit} more entries in the JSON inventory._"
    return f"{header}\n{body}{suffix}" if body else f"{header}\n"


def build_inventory(version: str) -> dict[str, Any]:
    pyproject = load_toml(ROOT / "pyproject.toml")
    uv_lock = load_toml(ROOT / "uv.lock") if (ROOT / "uv.lock").exists() else {}
    package_json = load_json(ROOT / "ui" / "package.json")
    package_lock = load_json(ROOT / "ui" / "package-lock.json")

    tool_checks = [
        ToolCheck("python", sys.executable, [sys.executable, "--version"]),
        ToolCheck("uv", "uv", ["uv", "--version"]),
        ToolCheck("node", "node", ["node", "--version"]),
        ToolCheck("npm", "npm", ["npm", "--version"]),
    ]
    agent_checks = [
        ToolCheck("claude-code", "claude", ["claude", "--version"]),
        ToolCheck("codex-cli", "codex", ["codex", "--version"]),
        ToolCheck("openclaw", "openclaw", ["openclaw", "--version"]),
        ToolCheck("hermes", "hermes", ["hermes", "--version"]),
    ]

    return {
        "schema_version": "1.0",
        "project": "micro-eval",
        "version": version,
        "generated_at": datetime.now().astimezone().isoformat(timespec="minutes"),
        "python": {
            "requires_python": pyproject.get("project", {}).get("requires-python"),
            "build_system": pyproject.get("build-system", {}),
            "project_dependencies": pyproject.get("project", {}).get("dependencies", []),
            "optional_dependencies": pyproject.get("project", {}).get("optional-dependencies", {}),
            "dependency_groups": pyproject.get("dependency-groups", {}),
            "resolved_packages": normalize_lock_packages(uv_lock),
        },
        "ui": {
            "package_name": package_json.get("name"),
            "package_version": package_json.get("version"),
            "dependencies": package_json.get("dependencies", {}),
            "dev_dependencies": package_json.get("devDependencies", {}),
            "lockfile_version": package_lock.get("lockfileVersion"),
            "lock_root_version": package_lock.get("version"),
            "resolved_packages": normalize_package_lock_packages(package_lock),
        },
        "tools": {check.name: run_tool(check.argv) for check in tool_checks},
        "external_agent_prerequisites": {check.name: run_tool(check.argv) for check in agent_checks},
        "notes": [
            "External agent CLI checks are best-effort availability/version checks only.",
            "Inventory intentionally does not record environment variables, tokens, account identifiers, or credential paths.",
        ],
    }


def write_markdown(inventory: dict[str, Any], path: Path, json_path: Path) -> None:
    python_packages = inventory["python"]["resolved_packages"]
    ui_packages = inventory["ui"]["resolved_packages"]
    lines = [
        "---",
        f"title: Dependency Inventory - v{inventory['version']}",
        "doc_type: release_evidence",
        "status: active",
        f"created_at: {inventory['generated_at']}",
        f"updated_at: {inventory['generated_at']}",
        "owner: micro-eval maintainers",
        "source_of_truth: false",
        "tags:",
        "  - release",
        "  - dependencies",
        "related:",
        f"  - {json_path.as_posix()}",
        "  - docs/engineering/release-process.md",
        "---",
        "",
        f"# Dependency Inventory - v{inventory['version']}",
        "",
        "This inventory records release dependency metadata without environment variables, tokens, account identifiers, or credential paths.",
        "",
        "## Toolchain",
        "",
        "| Tool | Available | Exit | Output |",
        "| --- | --- | --- | --- |",
    ]
    for name, info in inventory["tools"].items():
        output = (info.get("stdout") or info.get("stderr") or "").replace("\n", " ")
        lines.append(f"| `{name}` | `{info.get('available')}` | `{info.get('exit_code')}` | `{output}` |")

    lines += [
        "",
        "## Python package metadata",
        "",
        f"- Requires Python: `{inventory['python']['requires_python']}`",
        f"- Build system: `{inventory['python']['build_system'].get('build-backend')}`",
        "",
        "### Direct runtime dependencies",
        "",
    ]
    for dep in inventory["python"]["project_dependencies"]:
        lines.append(f"- `{dep}`")
    lines += ["", "### Resolved Python packages", "", markdown_table(python_packages, ("name", "version"), limit=80)]

    lines += [
        "",
        "## UI package metadata",
        "",
        f"- Package: `{inventory['ui']['package_name']}`",
        f"- Package version: `{inventory['ui']['package_version']}`",
        f"- Lockfile version: `{inventory['ui']['lockfile_version']}`",
        f"- Lock root version: `{inventory['ui']['lock_root_version']}`",
        "",
        "### UI dependencies",
        "",
    ]
    for name, version in sorted(inventory["ui"]["dependencies"].items()):
        lines.append(f"- `{name}`: `{version}`")
    lines += ["", "### UI dev dependencies", ""]
    for name, version in sorted(inventory["ui"]["dev_dependencies"].items()):
        lines.append(f"- `{name}`: `{version}`")
    lines += ["", "### Resolved UI packages", "", markdown_table(ui_packages, ("name", "version"), limit=120)]

    lines += [
        "",
        "## External agent prerequisites",
        "",
        "These tools are example prerequisites, not package dependencies.",
        "",
        "| Tool | Available | Exit | Output |",
        "| --- | --- | --- | --- |",
    ]
    for name, info in inventory["external_agent_prerequisites"].items():
        output = (info.get("stdout") or info.get("stderr") or "").replace("\n", " ")
        lines.append(f"| `{name}` | `{info.get('available')}` | `{info.get('exit_code')}` | `{output}` |")

    lines += ["", "## Notes", ""]
    for note in inventory["notes"]:
        lines.append(f"- {note}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=(ROOT / "VERSION").read_text(encoding="utf-8").strip())
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    inventory = build_inventory(args.version)
    release_dir = ROOT / "docs" / "releases"
    release_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{args.date}-v{args.version}-dependency-inventory"
    json_path = release_dir / f"{prefix}.json"
    md_path = release_dir / f"{prefix}.md"
    json_path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(inventory, md_path, json_path.relative_to(ROOT))
    print(md_path.relative_to(ROOT))
    print(json_path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

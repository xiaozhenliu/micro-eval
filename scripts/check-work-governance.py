#!/usr/bin/env python3
"""Validate the development work register and local ticket contract."""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LANES = ("Now", "Next", "Waiting", "Roadmap", "Inbox")
ACTIVE_LANES = ("Now", "Next", "Waiting")
LANE_ALIASES = {
    "Now": "Now",
    "Next": "Next",
    "Waiting": "Waiting",
    "Roadmap": "Roadmap",
    "Inbox": "Inbox",
    "当前执行（Now）": "Now",
    "下一步（Next）": "Next",
    "等待解除（Waiting）": "Waiting",
    "路线图（Roadmap）": "Roadmap",
    "收件箱（Inbox）": "Inbox",
}
TICKET_STATUSES = {"inbox", "ready", "in_progress", "blocked", "resolved", "archived"}
TRIAGE_ROLES = {
    "needs-triage",
    "needs-info",
    "ready-for-agent",
    "ready-for-human",
    "wontfix",
}
EXECUTORS = {"unassigned", "agent", "human", "pair"}
TICKET_TYPES = {"task", "research", "prototype", "grilling", "governance"}
TERMINAL_STATUSES = {"resolved", "archived"}
POINTER_RE = re.compile(
    r"\b(?:LOCAL-[A-Z0-9]+(?:-[A-Z0-9]+)*-[0-9]{2}|GH-[0-9]+)\b"
)
LOCAL_ID_RE = re.compile(r"^LOCAL-[A-Z0-9]+(?:-[A-Z0-9]+)*-[0-9]{2}$")
TICKET_FILENAME_RE = re.compile(r"^[0-9]{2}-[a-z0-9][a-z0-9-]*\.md$")
FIELD_RE = re.compile(r"^(?:\*\*)?([A-Za-z][A-Za-z _-]*)(?:\*\*)?\s*:\s*(.*?)\s*$")
DISALLOWED_SCRATCH_PARTS = {
    ".git",
    ".next",
    ".pytest_cache",
    ".vite",
    "__pycache__",
    "build",
    "cache",
    "dist",
    "node_modules",
    "runtime",
}
DISALLOWED_SCRATCH_SUFFIXES = (
    ".db",
    ".key",
    ".log",
    ".pem",
    ".pyc",
    ".sqlite",
)


@dataclass(frozen=True)
class Ticket:
    path: Path
    identifier: str
    status: str
    triage: str
    executor: str
    blocked_by: str


def _git(root: Path, *args: str) -> tuple[int, str, str]:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        match = FIELD_RE.match(line.strip())
        if match:
            fields[match.group(1).lower().replace(" ", "_")] = match.group(2)
    return fields


def _ticket_paths(root: Path) -> list[Path]:
    scratch = root / ".scratch"
    if not scratch.is_dir():
        return []
    return sorted(
        path
        for path in scratch.glob("*/issues/*.md")
        if path.is_file()
    )


def _read_tickets(root: Path) -> tuple[list[Ticket], list[str]]:
    tickets: list[Ticket] = []
    errors: list[str] = []
    identifiers: dict[str, Path] = {}
    for path in _ticket_paths(root):
        relative = path.relative_to(root).as_posix()
        if not TICKET_FILENAME_RE.fullmatch(path.name):
            errors.append(f"{relative}: filename must be NN-lowercase-kebab.md")
        fields = _fields(path.read_text(encoding="utf-8"))
        identifier = fields.get("id", "")
        ticket_type = fields.get("type", "")
        status = fields.get("status", "")
        triage = fields.get("triage", "")
        executor = fields.get("executor", "")
        blocked_by = fields.get("blocked_by", "")
        if not LOCAL_ID_RE.fullmatch(identifier):
            errors.append(f"{relative}: invalid or missing ID")
        elif identifier in identifiers:
            errors.append(
                f"{relative}: duplicate ID {identifier} also used by "
                f"{identifiers[identifier].relative_to(root).as_posix()}"
            )
        else:
            identifiers[identifier] = path
        if status not in TICKET_STATUSES:
            errors.append(f"{relative}: invalid lifecycle Status {status!r}")
        if ticket_type not in TICKET_TYPES:
            errors.append(f"{relative}: invalid Type {ticket_type!r}")
        if triage not in TRIAGE_ROLES:
            errors.append(f"{relative}: invalid Triage role {triage!r}")
        if executor not in EXECUTORS:
            errors.append(f"{relative}: invalid Executor {executor!r}")
        if not blocked_by:
            errors.append(f"{relative}: missing Blocked by field")
        elif blocked_by != "None":
            dependencies = [item.strip() for item in blocked_by.split(",")]
            if any(not POINTER_RE.fullmatch(item) for item in dependencies):
                errors.append(f"{relative}: Blocked by must use stable IDs")
        title = path.read_text(encoding="utf-8").splitlines()[:1]
        if not title or not identifier or not title[0].startswith(f"# {identifier} —"):
            errors.append(f"{relative}: heading must start with '# {identifier} —'")
        if status in TERMINAL_STATUSES and "## Completion evidence" not in path.read_text(
            encoding="utf-8"
        ):
            errors.append(f"{relative}: terminal ticket needs Completion evidence")
        if identifier:
            tickets.append(
                Ticket(
                    path=path,
                    identifier=identifier,
                    status=status,
                    triage=triage,
                    executor=executor,
                    blocked_by=blocked_by,
                )
            )
    return tickets, errors


def _lane_bodies(text: str) -> dict[str, str]:
    heading_pattern = "|".join(re.escape(alias) for alias in LANE_ALIASES)
    matches = list(re.finditer(rf"^## ({heading_pattern})\s*$", text, re.M))
    bodies: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        bodies[LANE_ALIASES[match.group(1)]] = text[match.end() : end]
    return bodies


def _relative_link(root: Path, todos: Path, target: str) -> Path | None:
    if "://" in target:
        return None
    target = target.split("#", 1)[0]
    candidate = (todos.parent / target).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _check_todos(root: Path, tickets: list[Ticket]) -> list[str]:
    todos = root / "TODOS.md"
    if not todos.is_file():
        return ["TODOS.md: Work Register is missing"]
    text = todos.read_text(encoding="utf-8")
    errors: list[str] = []
    bodies = _lane_bodies(text)
    missing_lanes = [lane for lane in LANES if lane not in bodies]
    if missing_lanes:
        errors.append(f"TODOS.md: missing portfolio lanes {', '.join(missing_lanes)}")
    if re.search(r"^## (Blocked|Done)\s*$|^### P[0-9]+\s*$", text, re.M):
        errors.append("TODOS.md: use portfolio lanes, not Blocked/Done/Pn priority headings")
    if re.search(r"(?<![A-Za-z0-9])#[0-9]+\b", text):
        errors.append("TODOS.md: use GH-<number>, never a bare GitHub issue number")

    active_ids: set[str] = set()
    active_pointers: dict[str, str] = {}
    for lane in ACTIVE_LANES:
        body = bodies.get(lane, "")
        for line_number, line in enumerate(body.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped in {"*(none)*", "（无）", "(none)"}:
                continue
            if not stripped.startswith("-"):
                continue
            pointers = POINTER_RE.findall(stripped)
            if len(pointers) != 1:
                errors.append(
                    f"TODOS.md {lane} line {line_number}: exactly one LOCAL/GH pointer required"
                )
                continue
            pointer = pointers[0]
            if pointer in active_pointers:
                errors.append(f"TODOS.md: duplicate active pointer {pointer}")
            active_pointers[pointer] = lane
            if pointer.startswith("LOCAL-"):
                link = re.search(rf"\[{re.escape(pointer)}\]\(([^)]+)\)", stripped)
                if not link:
                    errors.append(f"TODOS.md: local pointer {pointer} must be a markdown link")
                    continue
                target = _relative_link(root, todos, link.group(1))
                if target is None or not target.is_file():
                    errors.append(f"TODOS.md: local pointer {pointer} target does not exist")
                    continue
                target_fields = _fields(target.read_text(encoding="utf-8"))
                target_status = target_fields.get("status", "")
                if target_fields.get("id") != pointer:
                    errors.append(f"TODOS.md: {pointer} link target has a different ID")
                if target_status in TERMINAL_STATUSES:
                    errors.append(f"TODOS.md: active pointer {pointer} targets {target_status}")
                if target_status == "blocked" and lane != "Waiting":
                    errors.append(f"TODOS.md: blocked pointer {pointer} belongs in Waiting")
                active_ids.add(pointer)
            else:
                issue_number = pointer.removeprefix("GH-")
                link = re.search(
                    rf"\[[^\]]*{re.escape(pointer)}[^\]]*\]\([^)]*/issues/{issue_number}(?:[?#][^)]*)?\)",
                    stripped,
                )
                if not link:
                    errors.append(f"TODOS.md: {pointer} must link to its GitHub Issue")

    for lane in ("Roadmap",):
        for line_number, line in enumerate(bodies.get(lane, "").splitlines(), start=1):
            stripped = line.strip()
            if not stripped.startswith("-"):
                continue
            if not re.search(
                r"(?:Trigger\s*/\s*promote\s+when|Trigger|Promote\s+when|触发/晋升时机|触发条件)\s*[:：]\*{0,2}",
                stripped,
                re.IGNORECASE,
            ):
                errors.append(f"TODOS.md {lane} line {line_number}: missing trigger/promote-when field")
            if not re.search(
                r"(?:Planning\s+state|规划状态)\s*[:：]\*{0,2}\s*(?:Roadmap|路线图)\s*(?:\([^)]*not\s+blocked[^)]*\)|（[^）]*(?:未\s*blocked|未阻塞)[^）]*）)",
                stripped,
                re.IGNORECASE,
            ):
                errors.append(f"TODOS.md {lane} line {line_number}: Roadmap item must say not blocked/未阻塞")

    for ticket in tickets:
        if ticket.status not in TERMINAL_STATUSES and ticket.identifier not in active_ids:
            errors.append(
                f"TODOS.md: non-terminal ticket {ticket.identifier} is not in Now/Next/Waiting"
            )
    if "GH-15" not in active_pointers:
        errors.append("TODOS.md: GH-15 must be present as a Work Register pointer")
    return errors


def _load_projection_module(root: Path) -> Any:
    module_path = root / "scripts" / "release" / "public_projection.py"
    spec = importlib.util.spec_from_file_location("micro_eval_public_projection", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load scripts/release/public_projection.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _check_scratch(root: Path) -> list[str]:
    scratch = root / ".scratch"
    errors: list[str] = []
    paths = sorted(
        path
        for path in scratch.rglob("*")
        if path.is_file() or path.is_symlink()
    ) if scratch.is_dir() else []
    if not paths:
        errors.append(".scratch/: no durable work records found")
    for path in paths:
        relative = path.relative_to(scratch)
        parts = relative.parts
        name = path.name.lower()
        if any(part in DISALLOWED_SCRATCH_PARTS for part in parts) or name.startswith(".env"):
            errors.append(f".scratch/{relative.as_posix()}: runtime/cache content is not allowed")
        if name.endswith(DISALLOWED_SCRATCH_SUFFIXES):
            errors.append(f".scratch/{relative.as_posix()}: runtime/secret suffix is not allowed")
        allowed = (
            (len(parts) == 2 and parts[1] in {"map.md", "spec.md"})
            or (
                len(parts) == 3
                and parts[1] == "issues"
                and TICKET_FILENAME_RE.fullmatch(parts[2]) is not None
            )
            or (len(parts) >= 3 and parts[1] == "attachments")
        )
        if not allowed:
            errors.append(
                f".scratch/{relative.as_posix()}: only ticket, spec, map, or attachment files are allowed"
            )

    code, tracked, stderr = _git(root, "ls-files", "--", ".scratch")
    if code != 0:
        errors.append(f"git ls-files .scratch failed: {stderr.strip()}")
    elif not tracked.strip():
        errors.append(".scratch/: records must be tracked on dev")
    code, untracked, stderr = _git(
        root, "ls-files", "--others", "--exclude-standard", "--", ".scratch"
    )
    if code != 0:
        errors.append(f"git ls-files --others .scratch failed: {stderr.strip()}")
    elif untracked.strip():
        errors.extend(f"{line}: untracked work record" for line in untracked.splitlines())
    code, _, stderr = _git(
        root, "check-ignore", "--no-index", "-q", ".scratch/governance-probe.md"
    )
    if code == 0:
        errors.append(".scratch/: root gitignore must not ignore work records")
    elif code not in {1}:
        errors.append(f"git check-ignore .scratch failed: {stderr.strip()}")

    try:
        module = _load_projection_module(root)
        policy = module.ProjectionPolicy.load(
            root / "scripts" / "release" / "public-projection.toml"
        )
        probe = ".scratch/governance-probe.md"
        if not module._matches_any(probe, policy.private_patterns):
            errors.append("public projection policy must classify .scratch/** as private")
        if module._matches_any(probe, policy.public_patterns):
            errors.append("public projection policy classifies .scratch/** as public")
        if not module._matches_any(probe, policy.forbidden_public):
            errors.append("public projection policy must forbid .scratch/** in public output")
        if not module._matches_any("TODOS.md", policy.private_patterns):
            errors.append("public projection policy must classify TODOS.md as private")
        if module._matches_any("TODOS.md", policy.public_patterns):
            errors.append("public projection policy classifies TODOS.md as public")
        if not module._matches_any("TODOS.md", policy.forbidden_public):
            errors.append("public projection policy must forbid TODOS.md in public output")
        plan = policy.plan(root, "WORKTREE")
        for path in paths:
            relative = path.relative_to(root).as_posix()
            if relative not in plan.private_paths:
                errors.append(f"{relative}: work record is not classified private in projection plan")
    except (OSError, RuntimeError, ValueError) as exc:
        errors.append(f"public projection policy could not be checked: {exc}")
    return errors


def check_repository(root: Path) -> list[str]:
    root = root.resolve()
    tickets, ticket_errors = _read_tickets(root)
    return [*ticket_errors, *_check_todos(root, tickets), *_check_scratch(root)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to the checkout containing this script)",
    )
    args = parser.parse_args(argv)
    errors = check_repository(args.root)
    if errors:
        print("Work governance check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Work governance check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

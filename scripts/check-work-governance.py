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
LOCAL_ID_RE = re.compile(r"^LOCAL-[A-Z0-9]+(?:-[A-Z0-9]+)*-([0-9]{2})$")
TICKET_FILENAME_RE = re.compile(r"^([0-9]{2})-[a-z0-9][a-z0-9-]*\.md$")
FRONTMATTER_DELIMITER = "---"
FRONTMATTER_KEY_RE = re.compile(r"^([a-z][a-z0-9_]*)\s*:\s*(.*?)\s*$")
TIMESTAMP_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}[+-][0-9]{2}:[0-9]{2}$")
EFFORT_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LEGACY_FIELD_RE = re.compile(
    r"^(?:\*\*)?(ID|Type|Status|Triage|Executor|Blocked by)(?:\*\*)?\s*:", re.IGNORECASE
)
TICKET_REQUIRED_FIELDS = (
    "id",
    "title",
    "effort",
    "type",
    "status",
    "triage",
    "executor",
    "blocked_by",
    "created_at",
    "updated_at",
)
TICKET_OPTIONAL_FIELDS = ("tags", "related")
TICKET_LIST_FIELDS = frozenset({"blocked_by", "tags", "related"})
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
    blocked_by: tuple[str, ...]


def _git(root: Path, *args: str) -> tuple[int, str, str]:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], list[str], list[str]]:
    """Parse the YAML subset used by work records: scalars and string lists.

    Returns the parsed fields, the body lines, and any structural errors. The
    parser is intentionally strict so an unsupported construct fails the check
    instead of being silently reinterpreted.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return {}, lines, ["must start with YAML front matter delimited by '---'"]
    end = next(
        (
            index
            for index in range(1, len(lines))
            if lines[index].strip() == FRONTMATTER_DELIMITER
        ),
        None,
    )
    if end is None:
        return {}, [], ["front matter is not terminated by '---'"]

    fields: dict[str, Any] = {}
    errors: list[str] = []
    current_key: str | None = None
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw[0].isspace():
            item = raw.strip()
            if current_key is None or not item.startswith("- "):
                errors.append(f"unsupported front matter line {raw.strip()!r}")
                continue
            bucket = fields.get(current_key)
            if not isinstance(bucket, list):
                errors.append(f"front matter key {current_key!r} mixes a scalar and a list")
                continue
            bucket.append(_unquote(item[2:].strip()))
            continue
        match = FRONTMATTER_KEY_RE.match(raw)
        if match is None:
            errors.append(f"unsupported front matter line {raw.strip()!r}")
            current_key = None
            continue
        key, value = match.group(1), match.group(2)
        if key in fields:
            errors.append(f"duplicate front matter key {key!r}")
        current_key = key
        if value == "":
            fields[key] = []
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            fields[key] = (
                [_unquote(item.strip()) for item in inner.split(",") if item.strip()]
                if inner
                else []
            )
            current_key = None
        else:
            fields[key] = _unquote(value)
            current_key = None
    return fields, lines[end + 1 :], errors


def _check_ticket_frontmatter(
    fields: dict[str, Any], body: list[str], effort: str, sequence: str
) -> list[str]:
    errors: list[str] = []
    known = set(TICKET_REQUIRED_FIELDS) | set(TICKET_OPTIONAL_FIELDS)
    for key in sorted(set(fields) - known):
        errors.append(f"unknown front matter key {key!r}")
    for key in TICKET_REQUIRED_FIELDS:
        if key not in fields:
            errors.append(f"missing front matter key {key!r}")
    for key in sorted(set(fields) & known):
        wants_list = key in TICKET_LIST_FIELDS
        if wants_list is not isinstance(fields[key], list):
            expected = "a list" if wants_list else "a scalar"
            errors.append(f"front matter key {key!r} must be {expected}")

    identifier = fields.get("id")
    if not isinstance(identifier, str) or not LOCAL_ID_RE.fullmatch(identifier):
        errors.append("invalid or missing id")
    elif LOCAL_ID_RE.fullmatch(identifier).group(1) != sequence:
        errors.append(f"id {identifier} does not match the file number {sequence}")

    ticket_effort = fields.get("effort")
    if not isinstance(ticket_effort, str) or not EFFORT_RE.fullmatch(ticket_effort):
        errors.append("invalid or missing effort")
    elif ticket_effort != effort:
        errors.append(f"effort {ticket_effort!r} does not match directory {effort!r}")

    for key, allowed, label in (
        ("type", TICKET_TYPES, "Type"),
        ("status", TICKET_STATUSES, "lifecycle Status"),
        ("triage", TRIAGE_ROLES, "Triage role"),
        ("executor", EXECUTORS, "Executor"),
    ):
        value = fields.get(key)
        if not isinstance(value, str) or value not in allowed:
            errors.append(f"invalid {label} {value!r}")

    for key in ("created_at", "updated_at"):
        value = fields.get(key)
        if not isinstance(value, str) or not TIMESTAMP_RE.fullmatch(value):
            errors.append(f"{key} must be an ISO-8601 minute-precision timestamp")

    blocked_by = fields.get("blocked_by")
    if isinstance(blocked_by, list) and any(
        not POINTER_RE.fullmatch(item) for item in blocked_by
    ):
        errors.append("blocked_by must use stable LOCAL/GH identifiers")

    title = fields.get("title")
    heading = next((line for line in body if line.startswith("# ")), None)
    if heading is None:
        errors.append("missing H1 heading")
    elif isinstance(identifier, str) and isinstance(title, str):
        expected = f"# {identifier} — {title}"
        if heading.strip() != expected:
            errors.append(f"heading must be {expected!r}")

    if any(LEGACY_FIELD_RE.match(line) for line in body):
        errors.append("body still uses legacy plain-text metadata lines")

    status = fields.get("status")
    if status in TERMINAL_STATUSES and "## Completion evidence" not in "\n".join(body):
        errors.append("terminal ticket needs Completion evidence")
    return errors


def _read_ticket(root: Path, path: Path) -> tuple[Ticket | None, list[str]]:
    relative = path.relative_to(root).as_posix()
    errors: list[str] = []
    filename = TICKET_FILENAME_RE.fullmatch(path.name)
    if filename is None:
        errors.append(f"{relative}: filename must be NN-lowercase-kebab.md")
    effort = path.relative_to(root / ".scratch").parts[0]
    fields, body, structural = _parse_frontmatter(path.read_text(encoding="utf-8"))
    errors.extend(f"{relative}: {error}" for error in structural)
    if structural and not fields:
        return None, errors
    errors.extend(
        f"{relative}: {error}"
        for error in _check_ticket_frontmatter(
            fields, body, effort, filename.group(1) if filename else ""
        )
    )
    identifier = fields.get("id")
    if not isinstance(identifier, str) or not LOCAL_ID_RE.fullmatch(identifier):
        return None, errors
    blocked_by = fields.get("blocked_by")
    return (
        Ticket(
            path=path,
            identifier=identifier,
            status=str(fields.get("status", "")),
            triage=str(fields.get("triage", "")),
            executor=str(fields.get("executor", "")),
            blocked_by=tuple(blocked_by) if isinstance(blocked_by, list) else (),
        ),
        errors,
    )


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
        ticket, ticket_errors = _read_ticket(root, path)
        errors.extend(ticket_errors)
        if ticket is None:
            continue
        relative = path.relative_to(root).as_posix()
        if ticket.identifier in identifiers:
            errors.append(
                f"{relative}: duplicate ID {ticket.identifier} also used by "
                f"{identifiers[ticket.identifier].relative_to(root).as_posix()}"
            )
        else:
            identifiers[ticket.identifier] = path
        tickets.append(ticket)
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
                target_fields, _, _ = _parse_frontmatter(target.read_text(encoding="utf-8"))
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
            or (
                len(parts) == 4
                and parts[1] == "issues"
                and parts[2] == "resolved"
                and TICKET_FILENAME_RE.fullmatch(parts[3]) is not None
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


def _archived_ticket_paths(root: Path) -> list[Path]:
    scratch = root / ".scratch"
    if not scratch.is_dir():
        return []
    return sorted(
        path
        for path in scratch.glob("*/issues/resolved/*.md")
        if path.is_file()
    )


def _check_archived_tickets(root: Path, active: list[Ticket]) -> list[str]:
    errors: list[str] = []
    active_ids = {ticket.identifier for ticket in active}
    seen: dict[str, Path] = {}
    for path in _archived_ticket_paths(root):
        relative = path.relative_to(root).as_posix()
        ticket, ticket_errors = _read_ticket(root, path)
        errors.extend(ticket_errors)
        if ticket is None:
            continue
        identifier = ticket.identifier
        if ticket.status not in TERMINAL_STATUSES:
            errors.append(f"{relative}: archived ticket must be resolved or archived")
        if identifier in active_ids:
            errors.append(
                f"{relative}: archived ID {identifier} duplicates an active ticket"
            )
        elif identifier in seen:
            errors.append(
                f"{relative}: duplicate ID {identifier} also used by "
                f"{seen[identifier].relative_to(root).as_posix()}"
            )
        else:
            seen[identifier] = path
    return errors


def check_repository(root: Path) -> list[str]:
    root = root.resolve()
    tickets, ticket_errors = _read_tickets(root)
    return [
        *ticket_errors,
        *_check_todos(root, tickets),
        *_check_scratch(root),
        *_check_archived_tickets(root, tickets),
    ]


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

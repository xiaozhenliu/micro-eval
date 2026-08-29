#!/usr/bin/env python3
"""Plan and verify micro-eval documentation-site updates from repository changes."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


MAP_PATH = Path(__file__).resolve().parents[1] / "references" / "site-impact-map.toml"
SITE_SECTIONS = ("guide", "reference", "examples")


class SiteUpdateError(RuntimeError):
    """Raised when the site-update workflow cannot proceed safely."""


@dataclass(frozen=True)
class Check:
    id: str
    cwd: str
    argv: tuple[str, ...]
    always: bool


@dataclass(frozen=True)
class Rule:
    id: str
    summary: str
    globs: tuple[str, ...]
    pages: tuple[str, ...]
    checks: tuple[str, ...]


@dataclass(frozen=True)
class ImpactMap:
    behavior_globs: tuple[str, ...]
    checks: tuple[Check, ...]
    rules: tuple[Rule, ...]

    @property
    def checks_by_id(self) -> dict[str, Check]:
        return {check.id: check for check in self.checks}


def _run(
    argv: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
    text: bool = True,
) -> subprocess.CompletedProcess[Any]:
    try:
        result = subprocess.run(
            list(argv),
            cwd=cwd,
            capture_output=True,
            text=text,
            check=False,
        )
    except OSError as exc:
        raise SiteUpdateError(f"could not run {' '.join(argv)}: {exc}") from exc
    if check and result.returncode != 0:
        stderr = result.stderr if text else result.stderr.decode("utf-8", "replace")
        raise SiteUpdateError(
            f"command failed ({result.returncode}): {' '.join(argv)}\n{stderr.strip()}"
        )
    return result


def _repo_root() -> Path:
    result = _run(("git", "rev-parse", "--show-toplevel"), cwd=Path.cwd())
    return Path(result.stdout.strip()).resolve()


def _normalize_path(value: str) -> str:
    path = value.replace(os.sep, "/")
    pure = PurePosixPath(path)
    if pure.is_absolute() or not path or any(part in ("", ".", "..") for part in pure.parts):
        raise SiteUpdateError(f"path must be repository-relative without traversal: {value!r}")
    return pure.as_posix()


def _matches(path: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _load_impact_map(path: Path = MAP_PATH) -> ImpactMap:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != 1:
        raise SiteUpdateError("site impact map version must be 1")

    checks = tuple(
        Check(
            id=item["id"],
            cwd=item["cwd"],
            argv=tuple(item["argv"]),
            always=bool(item.get("always", False)),
        )
        for item in raw.get("checks", [])
    )
    rules = tuple(
        Rule(
            id=item["id"],
            summary=item["summary"],
            globs=tuple(item["globs"]),
            pages=tuple(item["pages"]),
            checks=tuple(item.get("checks", [])),
        )
        for item in raw.get("rules", [])
    )
    behavior_globs = tuple(raw.get("behavior_globs", []))

    check_ids = [item.id for item in checks]
    rule_ids = [item.id for item in rules]
    if not behavior_globs or not checks or not rules:
        raise SiteUpdateError("site impact map must define behavior globs, checks, and rules")
    if len(check_ids) != len(set(check_ids)):
        raise SiteUpdateError("site impact map contains duplicate check ids")
    if len(rule_ids) != len(set(rule_ids)):
        raise SiteUpdateError("site impact map contains duplicate rule ids")

    known_checks = set(check_ids)
    for check in checks:
        cwd_parts = PurePosixPath(check.cwd).parts
        if (
            not check.argv
            or Path(check.cwd).is_absolute()
            or ".." in cwd_parts
            or (check.cwd != "." and not cwd_parts)
        ):
            raise SiteUpdateError(f"invalid check definition: {check.id}")
    for rule in rules:
        unknown = sorted(set(rule.checks) - known_checks)
        if unknown:
            raise SiteUpdateError(f"rule {rule.id} references unknown checks: {unknown}")
        for page in rule.pages:
            normalized = _normalize_path(page)
            if not normalized.startswith("site/") or not normalized.endswith(".md"):
                raise SiteUpdateError(f"rule {rule.id} has invalid candidate page: {page}")

    return ImpactMap(behavior_globs=behavior_globs, checks=checks, rules=rules)


def _decode_nul_paths(payload: bytes) -> set[str]:
    return {
        _normalize_path(item.decode("utf-8"))
        for item in payload.split(b"\0")
        if item
    }


def _collect_git_paths(repo: Path, base: str) -> tuple[str, tuple[str, ...]]:
    base_result = _run(
        ("git", "rev-parse", "--verify", f"{base}^{{commit}}"),
        cwd=repo,
    )
    base_commit = base_result.stdout.strip()
    diff = _run(
        (
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACDMRTUXB",
            "-z",
            base_commit,
            "--",
        ),
        cwd=repo,
        text=False,
    )
    untracked = _run(
        ("git", "ls-files", "--others", "--exclude-standard", "-z"),
        cwd=repo,
        text=False,
    )
    paths = _decode_nul_paths(diff.stdout) | _decode_nul_paths(untracked.stdout)
    return base_commit, tuple(sorted(paths))


def _locale_counterpart(path: str) -> str | None:
    if path == "site/index.md":
        return "site/zh/index.md"
    if path == "site/zh/index.md":
        return "site/index.md"
    if path.startswith("site/zh/"):
        candidate = "site/" + path.removeprefix("site/zh/")
    elif any(path.startswith(f"site/{section}/") for section in SITE_SECTIONS):
        candidate = "site/zh/" + path.removeprefix("site/")
    else:
        return None
    return candidate


def _locale_pair_issues(repo: Path) -> tuple[str, ...]:
    issues: set[str] = set()
    expected_pairs = [(repo / "site/index.md", repo / "site/zh/index.md")]
    for section in SITE_SECTIONS:
        english_root = repo / "site" / section
        chinese_root = repo / "site" / "zh" / section
        english = {
            path.relative_to(english_root).as_posix()
            for path in english_root.rglob("*.md")
        }
        chinese = {
            path.relative_to(chinese_root).as_posix()
            for path in chinese_root.rglob("*.md")
        }
        for relative in sorted(english - chinese):
            issues.add(f"missing site/zh/{section}/{relative}")
        for relative in sorted(chinese - english):
            issues.add(f"missing site/{section}/{relative}")
    for english, chinese in expected_pairs:
        if english.exists() and not chinese.exists():
            issues.add("missing site/zh/index.md")
        if chinese.exists() and not english.exists():
            issues.add("missing site/index.md")
    return tuple(sorted(issues))


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _build_plan(
    repo: Path,
    impact_map: ImpactMap,
    *,
    base: str,
    paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    if paths is None:
        base_commit, changed_paths = _collect_git_paths(repo, base)
        mode = "git"
    else:
        base_commit = _run(
            ("git", "rev-parse", "--verify", f"{base}^{{commit}}"), cwd=repo
        ).stdout.strip()
        changed_paths = tuple(sorted({_normalize_path(path) for path in paths}))
        mode = "paths"

    behavior_paths = tuple(
        path for path in changed_paths if _matches(path, impact_map.behavior_globs)
    )
    site_paths = tuple(path for path in changed_paths if path.startswith("site/"))
    matched_rules: list[dict[str, Any]] = []
    mapped_paths: set[str] = set()
    candidate_pages: set[str] = set()
    check_ids = {check.id for check in impact_map.checks if check.always}

    for rule in impact_map.rules:
        matches = tuple(path for path in behavior_paths if _matches(path, rule.globs))
        if not matches:
            continue
        mapped_paths.update(matches)
        candidate_pages.update(rule.pages)
        check_ids.update(rule.checks)
        matched_rules.append(
            {
                "id": rule.id,
                "summary": rule.summary,
                "changed_paths": list(matches),
                "candidate_pages": list(rule.pages),
                "checks": list(rule.checks),
            }
        )

    missing_pages = tuple(
        page for page in sorted(candidate_pages) if not (repo / page).is_file()
    )
    unmapped = tuple(path for path in behavior_paths if path not in mapped_paths)
    other_paths = tuple(
        path
        for path in changed_paths
        if path not in behavior_paths and path not in site_paths
    )
    plan_core: dict[str, Any] = {
        "version": 1,
        "mode": mode,
        "base": base,
        "base_commit": base_commit,
        "changed_paths": list(changed_paths),
        "behavior_paths": list(behavior_paths),
        "changed_site_paths": list(site_paths),
        "other_paths": list(other_paths),
        "matched_rules": matched_rules,
        "candidate_pages": sorted(candidate_pages),
        "checks": sorted(check_ids),
        "unmapped_behavior_paths": list(unmapped),
        "missing_candidate_pages": list(missing_pages),
        "locale_pair_issues": list(_locale_pair_issues(repo)),
    }
    return {**plan_core, "fingerprint": _fingerprint(plan_core)}


def _resolution_skeleton(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": 1,
        "plan_fingerprint": plan["fingerprint"],
        "resolutions": [
            {
                "rule_id": rule["id"],
                "outcome": "pending",
                "pages": [],
                "rationale": "",
            }
            for rule in plan["matched_rules"]
        ],
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SiteUpdateError(f"could not read JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SiteUpdateError(f"expected a JSON object in {path}")
    return value


def _plan_failures(plan: dict[str, Any]) -> tuple[str, ...]:
    failures = []
    for key, label in (
        ("unmapped_behavior_paths", "unmapped behavior path"),
        ("missing_candidate_pages", "missing candidate page"),
        ("locale_pair_issues", "locale pair issue"),
    ):
        failures.extend(f"{label}: {value}" for value in plan[key])
    return tuple(failures)


def _render_plan(plan: dict[str, Any], impact_map: ImpactMap) -> str:
    checks = impact_map.checks_by_id
    lines = [
        "# micro-eval site update plan",
        "",
        f"- Base: `{plan['base']}` (`{plan['base_commit']}`)",
        f"- Changed paths: {len(plan['changed_paths'])}",
        f"- Behavior paths: {len(plan['behavior_paths'])}",
        f"- Impact rules: {len(plan['matched_rules'])}",
        "",
    ]
    if not plan["matched_rules"]:
        lines.extend(["No mapped user-facing behavior changes were found.", ""])
    for rule in plan["matched_rules"]:
        lines.extend(
            [
                f"## {rule['id']}",
                "",
                rule["summary"],
                "",
                "Changed authority files:",
                *[f"- `{path}`" for path in rule["changed_paths"]],
                "",
                "Candidate pages:",
                *[f"- `{page}`" for page in rule["candidate_pages"]],
                "",
            ]
        )
    lines.extend(["## Verification commands", ""])
    for check_id in plan["checks"]:
        check = checks[check_id]
        lines.append(f"- `({check.cwd}) {' '.join(check.argv)}`")
    failures = _plan_failures(plan)
    if failures:
        lines.extend(["", "## Blocking findings", "", *[f"- {item}" for item in failures]])
    return "\n".join(lines).rstrip() + "\n"


def _validate_resolution(
    plan: dict[str, Any],
    current_plan: dict[str, Any],
    resolution: dict[str, Any],
) -> tuple[str, ...]:
    failures = list(_plan_failures(current_plan))
    if resolution.get("version") != 1:
        failures.append("resolution version must be 1")
    if resolution.get("plan_fingerprint") != plan.get("fingerprint"):
        failures.append("resolution does not belong to this plan")
    if current_plan["base_commit"] != plan["base_commit"]:
        failures.append("comparison base moved after planning; regenerate the plan")
    if current_plan["behavior_paths"] != plan["behavior_paths"]:
        failures.append("behavior changes moved after planning; regenerate the plan")
    if current_plan["matched_rules"] != plan["matched_rules"]:
        failures.append("impact mapping changed after planning; regenerate the plan")

    expected_rules = {rule["id"]: rule for rule in plan["matched_rules"]}
    entries = resolution.get("resolutions")
    if not isinstance(entries, list):
        return tuple((*failures, "resolution entries must be a list"))
    seen: set[str] = set()
    changed = set(current_plan["changed_paths"])

    for entry in entries:
        if not isinstance(entry, dict):
            failures.append("each resolution entry must be an object")
            continue
        rule_id = entry.get("rule_id")
        if rule_id in seen:
            failures.append(f"duplicate resolution: {rule_id}")
            continue
        seen.add(rule_id)
        rule = expected_rules.get(rule_id)
        if rule is None:
            failures.append(f"resolution references unknown rule: {rule_id}")
            continue
        outcome = entry.get("outcome")
        rule_candidates = set(rule["candidate_pages"])
        pages = entry.get("pages")
        rationale = entry.get("rationale")
        if not isinstance(pages, list) or not all(isinstance(page, str) for page in pages):
            failures.append(f"resolution {rule_id} pages must be a string list")
            continue
        normalized_pages = [_normalize_path(page) for page in pages]
        if not isinstance(rationale, str) or not rationale.strip():
            failures.append(f"resolution {rule_id} requires a rationale")
        if outcome == "updated":
            if not normalized_pages:
                failures.append(f"resolution {rule_id} declares updated without pages")
            for page in normalized_pages:
                if page not in rule_candidates:
                    failures.append(f"resolution {rule_id} uses non-candidate page: {page}")
                if page not in changed:
                    failures.append(f"resolution {rule_id} page is absent from diff: {page}")
                counterpart = _locale_counterpart(page)
                if counterpart and counterpart in rule_candidates:
                    if counterpart not in normalized_pages:
                        failures.append(
                            f"resolution {rule_id} omits locale counterpart: {counterpart}"
                        )
                    elif counterpart not in changed:
                        failures.append(
                            f"resolution {rule_id} counterpart is absent from diff: {counterpart}"
                        )
        elif outcome == "no-doc-impact":
            if normalized_pages:
                failures.append(f"resolution {rule_id} no-doc-impact must not list pages")
        else:
            failures.append(f"resolution {rule_id} has incomplete outcome: {outcome}")

    missing = sorted(set(expected_rules) - seen)
    failures.extend(f"missing resolution: {rule_id}" for rule_id in missing)
    return tuple(failures)


def _execute_checks(repo: Path, plan: dict[str, Any], impact_map: ImpactMap) -> None:
    diff_check = subprocess.run(
        ["git", "diff", "--check", plan["base_commit"], "--"], cwd=repo, check=False
    )
    if diff_check.returncode != 0:
        raise SiteUpdateError("git diff --check failed")

    checks = impact_map.checks_by_id
    for check_id in plan["checks"]:
        check = checks[check_id]
        command = " ".join(check.argv)
        print(f"[verify] ({check.cwd}) {command}", flush=True)
        try:
            result = subprocess.run(
                list(check.argv), cwd=repo / check.cwd, check=False
            )
        except OSError as exc:
            raise SiteUpdateError(
                f"could not run verification check {check_id}: {exc}"
            ) from exc
        if result.returncode != 0:
            raise SiteUpdateError(f"verification check failed: {check_id}")


def _command_plan(args: argparse.Namespace) -> int:
    repo = _repo_root()
    impact_map = _load_impact_map()
    plan = _build_plan(
        repo,
        impact_map,
        base=args.base,
        paths=args.path if args.path else None,
    )
    _write_json(args.plan, plan)
    _write_json(args.resolution, _resolution_skeleton(plan))
    if args.format == "json":
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print(_render_plan(plan, impact_map), end="")
    failures = _plan_failures(plan)
    if args.strict and failures:
        return 2
    return 0


def _command_resolve(args: argparse.Namespace) -> int:
    payload = _read_json(args.resolution)
    entries = payload.get("resolutions")
    if not isinstance(entries, list):
        raise SiteUpdateError("resolution entries must be a list")
    matches = [entry for entry in entries if entry.get("rule_id") == args.rule]
    if len(matches) != 1:
        raise SiteUpdateError(f"expected one resolution entry for rule {args.rule}")
    matches[0].update(
        outcome=args.outcome,
        pages=[_normalize_path(page) for page in args.page],
        rationale=args.rationale.strip(),
    )
    _write_json(args.resolution, payload)
    return 0


def _command_verify(args: argparse.Namespace) -> int:
    repo = _repo_root()
    impact_map = _load_impact_map()
    plan = _read_json(args.plan)
    resolution = _read_json(args.resolution)
    if plan.get("version") != 1 or plan.get("mode") != "git":
        raise SiteUpdateError("verify requires a version 1 plan created from git changes")
    fingerprint_payload = {key: value for key, value in plan.items() if key != "fingerprint"}
    if _fingerprint(fingerprint_payload) != plan.get("fingerprint"):
        raise SiteUpdateError("plan fingerprint is invalid")
    current_plan = _build_plan(repo, impact_map, base=plan["base"])
    failures = _validate_resolution(plan, current_plan, resolution)
    if failures:
        detail = "\n  ".join(failures)
        raise SiteUpdateError(f"site update verification failed:\n  {detail}")
    if not args.skip_checks:
        _execute_checks(repo, current_plan, impact_map)
    print(
        json.dumps(
            {
                "status": "verified",
                "impact_rules": len(plan["matched_rules"]),
                "checks": [] if args.skip_checks else current_plan["checks"],
            },
            sort_keys=True,
        )
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="analyze changes and create a resolution ledger")
    plan_parser.add_argument("--base", default="HEAD")
    plan_parser.add_argument("--path", action="append", default=[])
    plan_parser.add_argument("--plan", type=Path, required=True)
    plan_parser.add_argument("--resolution", type=Path, required=True)
    plan_parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    plan_parser.add_argument("--strict", action="store_true")
    plan_parser.set_defaults(handler=_command_plan)

    resolve_parser = subparsers.add_parser("resolve", help="record one impact-rule outcome")
    resolve_parser.add_argument("--resolution", type=Path, required=True)
    resolve_parser.add_argument("--rule", required=True)
    resolve_parser.add_argument("--outcome", choices=("updated", "no-doc-impact"), required=True)
    resolve_parser.add_argument("--page", action="append", default=[])
    resolve_parser.add_argument("--rationale", required=True)
    resolve_parser.set_defaults(handler=_command_resolve)

    verify_parser = subparsers.add_parser("verify", help="verify coverage, diffs, and mapped checks")
    verify_parser.add_argument("--plan", type=Path, required=True)
    verify_parser.add_argument("--resolution", type=Path, required=True)
    verify_parser.add_argument("--skip-checks", action="store_true", help=argparse.SUPPRESS)
    verify_parser.set_defaults(handler=_command_verify)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except SiteUpdateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

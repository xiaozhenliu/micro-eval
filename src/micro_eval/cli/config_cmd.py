"""`micro-eval config` command group: read/write eval.yaml and task files.

Thin typer wrapper around micro_eval.config.editor. All commands take
`--project <dir>` (the eval project root; in server mode this is the
workspace directory) and never invoke a shell or another subprocess.

Error contract (consumed by ui/src/lib/project-api.ts): on failure a single
JSON object is printed to stderr, ``{"error": "<message>", "kind": <kind>}``,
and the exit code is 1. ``kind`` is ``validation`` (bad input, maps to 400),
``not_found`` (404) or ``internal`` (502). Messages never contain absolute
paths.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NoReturn

import typer
from pydantic import ValidationError

from micro_eval.config.editor import (
    CONFLICT,
    INTERNAL,
    NOT_FOUND,
    VALIDATION,
    ConfigEditError,
    build_project_draft,
    format_validation_error,
    remove_configuration,
    remove_task,
    resolve_project_dir,
    set_raw_config,
    set_task,
    show_raw_config,
    upsert_configuration,
)

config_app = typer.Typer(name="config", help="Read and edit eval.yaml configurations and tasks.")


def _fail(message: str, kind: str) -> NoReturn:
    typer.echo(json.dumps({"error": message, "kind": kind}), err=True)
    raise typer.Exit(1)


def _guarded(action: Callable[[], None]) -> None:
    """Run an editor action, mapping every failure to the JSON error contract."""
    try:
        action()
    except ConfigEditError as exc:
        _fail(str(exc), exc.kind)
    except ValidationError as exc:
        _fail(format_validation_error(exc), VALIDATION)
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001 - last-resort guard, keeps stderr JSON-only
        _fail(f"internal error ({type(exc).__name__})", INTERNAL)


def _resolve_project_or_exit(project: str) -> Path:
    try:
        return resolve_project_dir(project)
    except ConfigEditError as exc:
        _fail(str(exc), exc.kind)


def _read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        _fail("stdin must contain a single JSON object", VALIDATION)
    if not isinstance(payload, dict):
        _fail("stdin JSON must be an object", VALIDATION)
    return payload


def _print_draft(project_dir: Path) -> None:
    draft: dict[str, Any] = {}

    def build() -> None:
        draft.update(build_project_draft(project_dir))

    _guarded(build)
    typer.echo(json.dumps(draft, indent=2, sort_keys=False))


PROJECT_OPTION = typer.Option(..., "--project", help="Project root directory")
MEMBER_OPTION = typer.Option(None, "--member", help="Member performing the write (recorded in .micro-eval/config-audit.jsonl)")
ACTIVE_ONLY_OPTION = typer.Option(
    False,
    "--active-workspace-only",
    help="Team Server: hold the workspace lock and refuse unless workspace.json says status=active.",
)


@contextmanager
def _active_workspace(project_dir: Path, required: bool) -> Iterator[None]:
    """Serialise the write with archive/delete and refuse non-active workspaces.

    Takes the same ``workspace.lock`` that archiving takes (then the editor
    takes ``config.lock`` inside), so a workspace cannot be archived between
    the status check and the write (round-11 review, 2026-09-13).
    """
    if not required:
        yield
        return
    from micro_eval.server.models import WorkspaceMeta
    from micro_eval.server.workspace import WorkspaceError, WorkspaceManager

    try:
        with WorkspaceManager.lock(project_dir):
            meta_path = project_dir / "workspace.json"
            if meta_path.is_symlink() or not meta_path.is_file():
                _fail("workspace metadata not found", NOT_FOUND)
            try:
                meta = WorkspaceMeta.model_validate_json(meta_path.read_text())
            except ValueError:
                _fail("workspace metadata is invalid", INTERNAL)
            if meta.status != "active":
                _fail(f"workspace is {meta.status}; archived workspaces are read-only", CONFLICT)
            yield
    except WorkspaceError as exc:
        _fail(str(exc), INTERNAL)


@config_app.command(name="show")
def config_show(project: str = PROJECT_OPTION) -> None:
    """Print the project's configurations and tasks as JSON."""
    project_dir = _resolve_project_or_exit(project)
    _print_draft(project_dir)


@config_app.command(name="set-configuration")
def config_set_configuration(
    project: str = PROJECT_OPTION, member: str | None = MEMBER_OPTION, active_only: bool = ACTIVE_ONLY_OPTION
) -> None:
    """Upsert one configuration (JSON object on stdin) into eval.yaml."""
    project_dir = _resolve_project_or_exit(project)
    payload = _read_stdin_json()
    with _active_workspace(project_dir, active_only):
        _guarded(lambda: upsert_configuration(project_dir, payload, member=member))
    _print_draft(project_dir)


@config_app.command(name="remove-configuration")
def config_remove_configuration(
    project: str = PROJECT_OPTION,
    config_id: str = typer.Option(..., "--id", help="Configuration id to remove"),
    member: str | None = MEMBER_OPTION,
    active_only: bool = ACTIVE_ONLY_OPTION,
) -> None:
    """Remove a configuration by id."""
    project_dir = _resolve_project_or_exit(project)
    with _active_workspace(project_dir, active_only):
        _guarded(lambda: remove_configuration(project_dir, config_id, member=member))
    _print_draft(project_dir)


@config_app.command(name="set-task")
def config_set_task(
    project: str = PROJECT_OPTION, member: str | None = MEMBER_OPTION, active_only: bool = ACTIVE_ONLY_OPTION
) -> None:
    """Upsert one task (JSON object on stdin) as <tasks_dir>/<id>.yaml."""
    project_dir = _resolve_project_or_exit(project)
    payload = _read_stdin_json()
    with _active_workspace(project_dir, active_only):
        _guarded(lambda: set_task(project_dir, payload, member=member))
    _print_draft(project_dir)


@config_app.command(name="remove-task")
def config_remove_task(
    project: str = PROJECT_OPTION,
    task_id: str | None = typer.Option(None, "--id", help="Task id to remove (matched against each task file's id)"),
    path: str | None = typer.Option(None, "--path", help="Project-relative task file path to remove"),
    member: str | None = MEMBER_OPTION,
    active_only: bool = ACTIVE_ONLY_OPTION,
) -> None:
    """Remove a task by id or by project-relative path."""
    project_dir = _resolve_project_or_exit(project)
    with _active_workspace(project_dir, active_only):
        _guarded(lambda: remove_task(project_dir, task_id=task_id, path=path, member=member))
    _print_draft(project_dir)


@config_app.command(name="show-raw")
def config_show_raw(project: str = PROJECT_OPTION) -> None:
    """Print eval.yaml text (declared secret values redacted) as JSON."""
    project_dir = _resolve_project_or_exit(project)
    result: dict[str, Any] = {}
    _guarded(lambda: result.update(show_raw_config(project_dir)))
    typer.echo(json.dumps(result))


@config_app.command(name="set-raw")
def config_set_raw(
    project: str = PROJECT_OPTION, member: str | None = MEMBER_OPTION, active_only: bool = ACTIVE_ONLY_OPTION
) -> None:
    """Validate hand-edited eval.yaml text (JSON {"content": ...} on stdin) and write it verbatim."""
    project_dir = _resolve_project_or_exit(project)
    payload = _read_stdin_json()
    content = payload.get("content")
    if not isinstance(content, str):
        _fail("content must be a string", VALIDATION)
    with _active_workspace(project_dir, active_only):
        _guarded(lambda: set_raw_config(project_dir, content, member=member))
    typer.echo(json.dumps({"saved": True}))

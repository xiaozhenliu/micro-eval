"""GitWorktreeProvider: Level 0 (logical) isolation via git worktrees."""

from __future__ import annotations

import os
import difflib
import selectors
import shutil
import stat
import subprocess
from pathlib import Path

from micro_eval.engine.command import resolve_command_argv
from micro_eval.engine.providers.base import (
    CommandResult,
    IsolationLevel,
    WorkspaceHandle,
    WorkspaceProvider,
)
from micro_eval.models.environment import WorkspaceObservation
from micro_eval.models.ids import safe_path_segment
from micro_eval.models.task import WorkspaceSpec, WorkspaceType


class GitWorktreeProvider:
    """Level 0 isolation: git worktrees / blank / file-copy workspaces.

    This provider encapsulates the original WorkspaceManager logic for
    creating isolated directories via git worktree, blank dirs, or file copies.
    """

    SETUP_ENV_KEYS = {
        "PATH",
        "HOME",
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "SYSTEMROOT",
    }

    @property
    def name(self) -> str:
        return "git_worktree"

    @property
    def supported_levels(self) -> list[IsolationLevel]:
        return [IsolationLevel.logical]

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root.resolve()

    def create(self, spec: WorkspaceSpec, *, cell_id: str, run_id: str) -> WorkspaceHandle:
        workspace_root = self._project_root / ".micro-eval" / "workspaces" / safe_path_segment(run_id)
        safe_cell = safe_path_segment(cell_id)
        source_repo: Path | None = None
        source_commit: str | None = None

        if spec.type == WorkspaceType.git_repo:
            source_repo = self._resolve_source_path(spec.path)
            source_commit = _resolve_git_commit(source_repo, spec.ref)
            workspace_path = self._create_git_worktree(
                source_repo, source_commit, safe_cell, workspace_root
            )
        elif spec.type == WorkspaceType.files:
            workspace_path = self._create_local_workspace_dir(safe_cell, workspace_root)
            self._copy_files(spec, workspace_path)
        else:
            workspace_path = self._create_local_workspace_dir(safe_cell, workspace_root)

        setup_exit_code: int | None = None
        if spec.setup:
            setup_exit_code = self._run_setup(spec.setup, workspace_path)

        setup_modified = (
            spec.type == WorkspaceType.git_repo
            and bool(spec.setup)
            and self._has_non_ignored_changes(workspace_path, base_commit=source_commit)
        )

        return WorkspaceHandle(
            workspace_path=workspace_path,
            provider_name=self.name,
            isolation_level=IsolationLevel.logical,
            source_repo=source_repo,
            workspace_type=spec.type,
            setup_exit_code=setup_exit_code,
            metadata={
                **({"source_commit": source_commit} if source_commit else {}),
                **({"setup_modified": "true"} if setup_modified else {}),
            },
        )

    def exec_command(
        self,
        handle: WorkspaceHandle,
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> CommandResult:
        if not argv or not all(isinstance(a, str) and a for a in argv):
            raise ValueError("exec_command requires a non-empty argv list of non-empty strings")
        try:
            result = subprocess.run(
                argv,
                cwd=handle.workspace_path,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_s,
            )
            return CommandResult(
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(exit_code=-1, timed_out=True)

    def collect_artifacts(self, handle: WorkspaceHandle) -> list:
        """Legacy compatibility shim; Environment no longer creates artifacts."""
        return []

    def collect_diff(self, handle: WorkspaceHandle) -> str | None:
        """Legacy raw-diff shim retained for callers predating observe_final()."""
        return self.observe_final(handle, byte_limit=50 * 1024 * 1024).diff_text

    def observe_final(self, handle: WorkspaceHandle, *, byte_limit: int) -> WorkspaceObservation:
        """Collect bounded, raw terminal facts while the workspace is live."""
        warnings: list[str] = []
        if handle.metadata.get("setup_modified") == "true":
            warnings.append("diff_includes_setup_changes")

        if handle.workspace_type != WorkspaceType.git_repo:
            return WorkspaceObservation(workspace_type=handle.workspace_type, warnings=tuple(warnings))

        limit = max(0, byte_limit)
        return self._observe_git_diff(handle, limit, warnings)

    def snapshot(self, handle: WorkspaceHandle) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=handle.workspace_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""

    def restore(self, handle: WorkspaceHandle, snap: str) -> None:
        raise NotImplementedError("restore not supported for git worktree provider")

    def cleanup(self, handle: WorkspaceHandle) -> None:
        if handle.source_repo is not None:
            try:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(handle.workspace_path)],
                    cwd=handle.source_repo,
                    capture_output=True,
                    check=True,
                )
                subprocess.run(
                    ["git", "worktree", "prune"],
                    cwd=handle.source_repo,
                    capture_output=True,
                    check=False,
                )
                return
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
        shutil.rmtree(handle.workspace_path, ignore_errors=True)

    def _resolve_source_path(self, path_value: str | None) -> Path:
        source = Path(path_value) if path_value else self._project_root
        if not source.is_absolute():
            source = self._project_root / source
        source = source.resolve()
        _assert_within_root(source, self._project_root)
        if not source.exists():
            raise WorkspaceProviderError(f"Workspace source does not exist: {source}")
        if not _is_git_repo(source):
            raise WorkspaceProviderError(f"Workspace source is not a git repository: {source}")
        return source

    def _create_local_workspace_dir(self, safe_cell: str, workspace_root: Path) -> Path:
        workspace_path = workspace_root / safe_cell
        if workspace_path.exists():
            raise WorkspaceProviderError(f"Workspace path already exists: {workspace_path}")
        workspace_path.mkdir(parents=True)
        return workspace_path

    def _create_git_worktree(
        self, source_repo: Path, commit: str, safe_cell: str, workspace_root: Path
    ) -> Path:
        workspace_path = workspace_root / safe_cell
        if workspace_path.exists():
            raise WorkspaceProviderError(f"Workspace path already exists: {workspace_path}")
        workspace_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(workspace_path), commit],
            cwd=source_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        return workspace_path

    def _copy_files(self, workspace: WorkspaceSpec, workspace_path: Path) -> None:
        paths = workspace.files or ([workspace.path] if workspace.path else [])
        for item in paths:
            source = Path(item)
            if not source.is_absolute():
                source = self._project_root / source
            source = source.resolve()
            _assert_within_root(source, self._project_root)
            if not source.exists():
                raise WorkspaceProviderError(f"Workspace file source does not exist: {source}")
            destination = workspace_path / source.name
            if source.is_dir():
                shutil.copytree(source, destination)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

    def _run_setup(self, setup: list[list[str]], workspace_path: Path) -> int:
        exit_code = 0
        for command in setup:
            if not command or any(not isinstance(part, str) or not part for part in command):
                raise WorkspaceProviderError("workspace setup commands must be non-empty argv lists")
            result = subprocess.run(
                resolve_command_argv(command),
                cwd=workspace_path,
                env={key: value for key, value in os.environ.items() if key in self.SETUP_ENV_KEYS},
                capture_output=True,
                text=True,
                check=False,
            )
            exit_code = result.returncode
            if exit_code != 0:
                break
        return exit_code

    def _has_non_ignored_changes(self, workspace_path: Path, *, base_commit: str | None) -> bool:
        base = base_commit or "HEAD"
        tracked = subprocess.run(
            ["git", "diff", "--quiet", base, "--"],
            cwd=workspace_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if tracked.returncode != 0:
            return True
        _, untracked, _ = _run_capped(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=workspace_path,
            byte_limit=1,
        )
        return bool(untracked)

    def _observe_git_diff(
        self, handle: WorkspaceHandle, byte_limit: int, warnings: list[str]
    ) -> WorkspaceObservation:
        excluded_paths, tracked_complete = self._tracked_exclusions(handle, byte_limit, warnings)
        pathspecs = [".", *(f":(exclude,literal){path}" for path in excluded_paths)]
        base_commit = handle.metadata.get("source_commit", "HEAD")
        if tracked_complete:
            tracked_code, tracked_bytes, tracked_truncated = _run_capped(
                [
                    "git", "diff", "--no-color", "--no-ext-diff",
                    base_commit, "--", *pathspecs,
                ],
                cwd=handle.workspace_path,
                byte_limit=byte_limit,
            )
            if tracked_code != 0:
                warnings.append("observation_unavailable")
                return WorkspaceObservation(
                    workspace_type=handle.workspace_type,
                    diff_truncated=tracked_truncated,
                    warnings=tuple(_unique(warnings)),
                )
        else:
            # Without a complete old/new mode inventory, including any
            # tracked diff would fail open for an unseen symlink, submodule,
            # or special entry. Sacrifice tracked text rather than persist
            # an unsafe body; untracked processing below remains independent.
            tracked_bytes = b""
            tracked_truncated = False
            warnings.append("tracked_diff_skipped")

        diff_bytes = bytearray(tracked_bytes)
        if tracked_truncated:
            warnings.append("diff_truncated")
            # Never persist a prefix of a tracked file: the retained prefix
            # may be an incomplete secret or an unsafe over-cap body.
            diff_bytes.clear()
            warnings.append("tracked_diff_skipped")
        if tracked_complete:
            _, numstat, numstat_truncated = _run_capped(
                [
                    "git", "diff", "--numstat", "--no-ext-diff", "-z",
                    base_commit, "--", *pathspecs,
                ],
                cwd=handle.workspace_path,
                byte_limit=byte_limit,
            )
            if b"\t-\t-\t" in numstat:
                warnings.append("tracked_binary_skipped")
            if numstat_truncated:
                warnings.append("tracked_change_listing_truncated")

        _, listing, listing_truncated = _run_capped(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=handle.workspace_path,
            byte_limit=byte_limit,
        )
        diff_truncated = tracked_truncated
        if listing_truncated:
            warnings.append("untracked_listing_truncated")
            # The final record may be a partial pathname. Do not interpret or
            # persist any untracked body when the inventory is incomplete.
            diff_truncated = True
            listing = b""

        remaining = max(0, byte_limit - len(diff_bytes))
        for raw_path in listing.split(b"\x00"):
            if not raw_path:
                continue
            relative = raw_path.decode(errors="surrogateescape")
            candidate = _safe_untracked_path(handle.workspace_path, relative, warnings)
            if candidate is None:
                continue
            try:
                file_stat = candidate.lstat()
            except OSError:
                warnings.append("untracked_file_unavailable")
                continue
            if file_stat.st_size > remaining:
                warnings.append("untracked_file_exceeds_diff_cap")
                diff_truncated = True
                continue
            try:
                data = _read_file_capped(candidate, remaining)
            except OSError:
                warnings.append("untracked_file_unavailable")
                continue
            if data is None:
                warnings.append("untracked_file_exceeds_diff_cap")
                diff_truncated = True
                continue
            if _looks_binary_file(data):
                warnings.append("untracked_binary_skipped")
                continue

            text = data.decode(errors="replace")
            generated = "".join(
                difflib.unified_diff(
                    [],
                    text.splitlines(keepends=True),
                    fromfile="/dev/null",
                    tofile=f"b/{relative}",
                )
            ).encode()
            if len(generated) > remaining:
                warnings.append("untracked_file_exceeds_diff_cap")
                diff_truncated = True
                continue
            diff_bytes.extend(generated)
            remaining -= len(generated)

        if len(diff_bytes) > byte_limit:
            # This is defensive: every append above is bounded, but the final
            # invariant is enforced at the Environment boundary as well.
            del diff_bytes[byte_limit:]
            diff_truncated = True
            warnings.append("diff_truncated")
        return WorkspaceObservation(
            workspace_type=handle.workspace_type,
            diff_text=bytes(diff_bytes).decode(errors="replace") or None,
            diff_truncated=diff_truncated,
            warnings=tuple(_unique(warnings)),
        )

    def _tracked_exclusions(
        self, handle: WorkspaceHandle, byte_limit: int, warnings: list[str]
    ) -> tuple[list[str], bool]:
        """Return changed tracked paths unsafe to include in a text diff."""
        tracked_modes, modes_complete = self._tracked_modes(handle, byte_limit, warnings)
        base_commit = handle.metadata.get("source_commit", "HEAD")
        _, changed, listing_truncated = _run_capped(
            ["git", "diff", "--no-renames", "--name-only", "-z", base_commit, "--"],
            cwd=handle.workspace_path,
            byte_limit=byte_limit,
        )
        if listing_truncated:
            warnings.append("tracked_change_listing_truncated")
        if not modes_complete or listing_truncated:
            return [], False

        excluded: list[str] = []
        for raw_path in changed.split(b"\x00"):
            if not raw_path:
                continue
            relative = raw_path.decode(errors="surrogateescape")
            relative_path = Path(relative)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                warnings.append("tracked_path_rejected")
                continue
            modes = tracked_modes.get(relative, ())
            if not modes:
                warnings.append("tracked_mode_unavailable")
                return [], False
            old_mode, _new_mode = modes
            special_modes = [mode for mode in modes if mode not in {"000000", "100644", "100755"}]
            if special_modes:
                if "120000" in special_modes:
                    warnings.append("tracked_symlink_skipped")
                elif "160000" in special_modes:
                    warnings.append("tracked_submodule_skipped")
                else:
                    warnings.append("tracked_special_file_skipped")
                excluded.append(relative)
                continue
            if old_mode != "000000":
                warning = self._head_blob_warning(handle, relative, byte_limit)
                if warning is not None:
                    warnings.append(warning)
                    excluded.append(relative)
                    continue
            candidate = handle.workspace_path / relative_path
            try:
                file_stat = candidate.lstat()
            except FileNotFoundError:
                # A deleted file is checked through the source HEAD below.
                code, data, truncated = _run_capped(
                    ["git", "show", f"{base_commit}:{relative}"],
                    cwd=handle.workspace_path,
                    byte_limit=byte_limit,
                )
                if code == 0 and (truncated or _looks_binary_file(data)):
                    warnings.append(
                        "tracked_file_exceeds_diff_cap" if truncated else "tracked_binary_skipped"
                    )
                    excluded.append(relative)
                continue
            except OSError:
                warnings.append("tracked_path_rejected")
                excluded.append(relative)
                continue

            if candidate.is_symlink():
                warnings.append("tracked_symlink_skipped")
                excluded.append(relative)
                continue
            if file_stat.st_nlink > 1:
                warnings.append("tracked_linked_file_skipped")
                excluded.append(relative)
                continue
            if not stat.S_ISREG(file_stat.st_mode):
                warnings.append("tracked_special_file_skipped")
                excluded.append(relative)
                continue
            if file_stat.st_size > byte_limit:
                warnings.append("tracked_file_exceeds_diff_cap")
                excluded.append(relative)
                continue
            try:
                data = _read_file_capped(candidate, byte_limit)
            except OSError:
                warnings.append("tracked_file_unavailable")
                excluded.append(relative)
                continue
            if data is None:
                warnings.append("tracked_file_exceeds_diff_cap")
                excluded.append(relative)
            elif _looks_binary_file(data):
                warnings.append("tracked_binary_skipped")
                excluded.append(relative)
        return excluded, True

    def _head_blob_warning(
        self, handle: WorkspaceHandle, relative: str, byte_limit: int
    ) -> str | None:
        """Classify a HEAD blob without retaining more than the diff cap."""
        base_commit = handle.metadata.get("source_commit", "HEAD")
        code, data, truncated = _run_capped(
            ["git", "show", f"{base_commit}:{relative}"],
            cwd=handle.workspace_path,
            byte_limit=byte_limit,
        )
        if code != 0:
            return "tracked_file_unavailable"
        if truncated:
            return "tracked_file_exceeds_diff_cap"
        if _looks_binary_file(data):
            return "tracked_binary_skipped"
        return None

    def _tracked_modes(
        self, handle: WorkspaceHandle, byte_limit: int, warnings: list[str]
    ) -> tuple[dict[str, tuple[str, str]], bool]:
        """Read old/new Git modes without reading changed file bodies."""
        _, raw, truncated = _run_capped(
            [
                "git", "diff", "--no-renames", "--raw", "-z",
                handle.metadata.get("source_commit", "HEAD"), "--",
            ],
            cwd=handle.workspace_path,
            byte_limit=byte_limit,
        )
        if truncated:
            warnings.append("tracked_change_listing_truncated")
        modes: dict[str, tuple[str, str]] = {}
        records = raw.split(b"\x00")
        index = 0
        while index < len(records):
            record = records[index]
            if not record:
                index += 1
                continue
            if b"\t" in record:
                header, raw_path = record.split(b"\t", 1)
            else:
                header = record
                index += 1
                if index >= len(records):
                    break
                raw_path = records[index]
            fields = header.split()
            if len(fields) < 2:
                index += 1
                continue
            old_mode = fields[0].lstrip(b":").decode(errors="replace")
            new_mode = fields[1].decode(errors="replace")
            modes[raw_path.decode(errors="surrogateescape")] = (old_mode, new_mode)
            index += 1
        return modes, not truncated


class WorkspaceProviderError(Exception):
    """Raised when a workspace provider operation fails."""


def _assert_within_root(source: Path, root: Path) -> None:
    try:
        source.relative_to(root)
    except ValueError:
        raise WorkspaceProviderError(
            f"Workspace source path escapes the project root: {source} "
            f"(project root: {root})"
        )


def _is_git_repo(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=path,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def _resolve_git_commit(repo: Path, ref: str | None) -> str:
    target = ref or "HEAD"
    try:
        result = subprocess.run(
            ["git", "rev-parse", target],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise WorkspaceProviderError(
            f"Failed to resolve git ref {target!r} in {repo}"
        ) from exc


def _run_capped(argv: list[str], *, cwd: Path, byte_limit: int) -> tuple[int, bytes, bool]:
    """Run a command while retaining at most *byte_limit* bytes of output."""
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, OSError):
        return 127, b"", False

    selector = selectors.DefaultSelector()
    for stream in (proc.stdout, proc.stderr):
        if stream is not None:
            selector.register(stream, selectors.EVENT_READ)
    retained_stdout = bytearray()
    truncated = False
    try:
        while selector.get_map():
            for key, _ in selector.select():
                data = os.read(key.fileobj.fileno(), 8192)
                if not data:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                if key.fileobj is proc.stdout:
                    remaining = max(0, byte_limit - len(retained_stdout))
                    if remaining:
                        retained_stdout.extend(data[:remaining])
                    if len(data) > remaining:
                        truncated = True
                # stderr is deliberately drained but never mixed into the
                # structured stdout used for diff/mode/path parsing.
    finally:
        selector.close()
    return proc.wait(), bytes(retained_stdout), truncated


def _safe_untracked_path(root: Path, relative: str, warnings: list[str]) -> Path | None:
    candidate = root / relative
    try:
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            warnings.append("untracked_path_rejected")
            return None
        file_stat = candidate.lstat()
        if candidate.is_symlink():
            warnings.append("untracked_symlink_skipped")
            return None
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink > 1:
            warnings.append("untracked_linked_file_skipped")
            return None
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve())
        return candidate
    except (OSError, ValueError):
        warnings.append("untracked_path_rejected")
        return None


def _read_file_capped(path: Path, byte_limit: int) -> bytes | None:
    with path.open("rb") as stream:
        data = stream.read(max(0, byte_limit) + 1)
    return None if len(data) > byte_limit else data


def _looks_binary_file(data: bytes) -> bool:
    return b"\x00" in data


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))

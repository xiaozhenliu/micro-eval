"""OS policy execution for local workspaces.

Seatbelt allows host reads; Bubblewrap exposes explicit read-only runtime roots.
Neither provider promises confidentiality from readable host files. Only the
current workspace and its dedicated output staging directory are host-writable.
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import sys
import tempfile
import textwrap
from dataclasses import replace
from pathlib import Path

from micro_eval.engine.command import resolve_command_argv
from micro_eval.engine.process_runner import run_process
from micro_eval.engine.providers.base import (
    CommandResult,
    ExecutionRequest,
    IsolationLevel,
    WorkspaceHandle,
)
from micro_eval.engine.providers.git_worktree import (
    GitWorktreeProvider,
    WorkspaceProviderError,
)
from micro_eval.models.environment import WorkspaceObservation
from micro_eval.models.task import WorkspaceSpec, WorkspaceType


class _OsPolicyProvider:
    platform_name: str
    executable: str
    provider_name: str

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root.resolve()
        self._inner = GitWorktreeProvider(project_root)
        self._available = (
            platform.system() == self.platform_name
            and shutil.which(self.executable) is not None
        )

    @property
    def name(self) -> str:
        return self.provider_name

    @property
    def supported_levels(self) -> list[IsolationLevel]:
        return [IsolationLevel.os_policy] if self._available else []

    def create(self, spec: WorkspaceSpec, *, cell_id: str, run_id: str) -> WorkspaceHandle:
        policy = _network_policy(spec.network_policy.value if spec.network_policy else "full")
        # Workspace materialization must never run setup on the host first.
        inner = self._inner.create(
            spec.model_copy(update={"setup": []}), cell_id=cell_id, run_id=run_id,
        )
        try:
            handle = replace(
                inner,
                provider_name=self.name,
                isolation_level=IsolationLevel.os_policy,
                metadata={
                    **inner.metadata,
                    "sandbox_type": self.name,
                    "network_policy": policy,
                    "network_policy_requested": policy,
                    "network_policy_effective": policy,
                    "filesystem_read_boundary": (
                        "host-readable-files" if self.name == "seatbelt" else
                        json.dumps([str(path) for path in _runtime_roots(self._project_root)])
                    ),
                },
            )
            if spec.setup:
                # The async lifecycle runs setup after preparing output. This
                # synchronous compatibility path has no output directory yet.
                with tempfile.TemporaryDirectory(prefix=".micro-eval-tmp-", dir=handle.workspace_path) as tmp:
                    env = {key: value for key, value in os.environ.items()
                           if key in GitWorktreeProvider.SETUP_ENV_KEYS}
                    env.update({"TMPDIR": tmp, "TEMP": tmp, "TMP": tmp})
                    for command in spec.setup:
                        result = self.exec_command(handle, resolve_command_argv(command), env=env)
                        handle.setup_exit_code = result.exit_code
                        if result.exit_code:
                            break
                if (spec.type == WorkspaceType.git_repo and self._inner._has_non_ignored_changes(
                    handle.workspace_path, base_commit=handle.metadata.get("source_commit"),
                )):
                    handle.metadata["setup_modified"] = "true"
            return handle
        except BaseException:
            self._inner.cleanup(inner)
            raise

    async def execute(self, handle: WorkspaceHandle, request: ExecutionRequest) -> CommandResult:
        if not request.argv or not all(isinstance(arg, str) and arg for arg in request.argv):
            raise ValueError("exec_command requires a non-empty argv list of non-empty strings")
        policy = _network_policy(handle.metadata.get("network_policy", "full"))
        output_path = _output_path(handle)
        cwd = request.cwd or handle.workspace_path
        argv = self._wrap(handle.workspace_path, policy, request.argv, output_path, cwd=cwd)
        return await run_process(replace(request, argv=argv, cwd=cwd))

    def _wrap(
        self, workspace: Path, policy: str, argv: list[str], output: Path | None, *, cwd: Path,
    ) -> list[str]:
        raise NotImplementedError

    def exec_command(
        self, handle: WorkspaceHandle, argv: list[str], *,
        env: dict[str, str] | None = None, timeout_s: float | None = None,
    ) -> CommandResult:
        if env is None:
            env = {key: value for key, value in os.environ.items()
                   if key in GitWorktreeProvider.SETUP_ENV_KEYS}
        return asyncio.run(self.execute(handle, ExecutionRequest(
            argv=argv, cwd=handle.workspace_path, env=env, timeout_s=timeout_s,
        )))

    def collect_artifacts(self, handle: WorkspaceHandle) -> list:
        """Legacy compatibility shim; Environment no longer creates artifacts."""
        return self._inner.collect_artifacts(handle)

    def collect_diff(self, handle: WorkspaceHandle) -> str | None:
        return self._inner.collect_diff(handle)

    def observe_final(self, handle: WorkspaceHandle, *, byte_limit: int) -> WorkspaceObservation:
        return self._inner.observe_final(handle, byte_limit=byte_limit)

    def snapshot(self, handle: WorkspaceHandle) -> str:
        return self._inner.snapshot(handle)

    def restore(self, handle: WorkspaceHandle, snap: str) -> None:
        raise NotImplementedError(f"restore not supported for {self.name} provider")

    def cleanup(self, handle: WorkspaceHandle) -> None:
        self._inner.cleanup(handle)


class SeatbeltProvider(_OsPolicyProvider):
    """macOS sandbox-exec filesystem-write and network restrictions."""

    platform_name = "Darwin"
    executable = "sandbox-exec"
    provider_name = "seatbelt"

    def _wrap(
        self, workspace: Path, policy: str, argv: list[str], output: Path | None, *, cwd: Path,
    ) -> list[str]:
        return ["sandbox-exec", "-p", _build_seatbelt_profile(workspace, policy, output), *argv]


class BubblewrapProvider(_OsPolicyProvider):
    """Linux Bubblewrap filesystem mounts and network namespace restrictions."""

    platform_name = "Linux"
    executable = "bwrap"
    provider_name = "bubblewrap"

    def _wrap(
        self, workspace: Path, policy: str, argv: list[str], output: Path | None, *, cwd: Path,
    ) -> list[str]:
        return _build_bwrap_argv(
            workspace, policy, argv, output, project_root=self._project_root, cwd=cwd,
        )


def _network_policy(policy: str) -> str:
    if policy not in {"full", "none"}:
        raise WorkspaceProviderError(
            f"OS policy network mode {policy!r} is unsupported; use full or none. "
            "allowlist requires explicit rules and is not implemented."
        )
    return policy


def _output_path(handle: WorkspaceHandle) -> Path | None:
    value = handle.metadata.get("output_path")
    if value is None:
        return None
    path = Path(value)
    if (path.is_symlink() or path.resolve().parent != handle.workspace_path.resolve().parent
            or not path.name.startswith(".micro-eval-io-") or not path.is_dir()):
        raise WorkspaceProviderError("OS policy output staging must be a dedicated workspace sibling")
    return path.resolve()


def _seatbelt_string(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace('"', '\\"')


def _build_seatbelt_profile(
    workspace_path: Path, network_policy: str, output_path: Path | None = None,
) -> str:
    """Allow host reads, but grant host writes only to these exact subtrees."""
    policy = _network_policy(network_policy)
    paths = [workspace_path, *([output_path] if output_path is not None else [])]
    write_rules = "\n".join(
        f'(allow file-write* (subpath "{_seatbelt_string(path)}"))' for path in paths
    )
    network_rule = "(allow network*)" if policy == "full" else "(deny network*)"
    return textwrap.dedent(f"""\
        (version 1)
        (deny default)
        (allow process*)
        (allow sysctl*)
        (allow mach*)
        (allow signal)
        (allow file-read*)
        {write_rules}
        (allow file-write-data (literal "/dev/null"))
        (allow file-write-data (literal "/dev/dtracehelper"))
        {network_rule}
    """)


def _runtime_roots(project_root: Path | None) -> list[Path]:
    """Read-only roots needed by system tools, host Python, venv and project code.

    A venv interpreter can point into a uv/pyenv installation outside /usr; both
    its logical prefix and resolved installation must remain executable. These
    mounts grant read access, never host write access, and are recorded in the
    provider handle instead of claiming a confidentiality boundary.
    """
    candidates = [Path(path) for path in ("/usr", "/bin", "/lib", "/lib64", "/etc")]
    candidates.extend([
        Path(sys.prefix), Path(sys.base_prefix), Path(sys.executable).resolve().parent.parent,
        Path(__file__).resolve().parents[3],
    ])
    # A managed venv can target a stable alias rather than the versioned
    # installation. Expose the alias only when it names an already allowed
    # runtime root, and preserve argv[0] so Python keeps its venv packages.
    base_executable = getattr(sys, "_base_executable", None) or sys.executable
    base_alias = Path(base_executable).absolute().parent.parent
    if base_alias.resolve() in {path.resolve() for path in candidates if path.exists()}:
        candidates.append(base_alias)
    if project_root is not None:
        candidates.append(project_root)
    return sorted({path.absolute() for path in candidates if path.exists()}, key=lambda p: (len(p.parts), str(p)))


def _build_bwrap_argv(
    workspace_path: Path, network_policy: str, inner_argv: list[str],
    output_path: Path | None = None, *, project_root: Path | None = None, cwd: Path | None = None,
) -> list[str]:
    """Mount runtime read-only before the two narrowly writable cell paths."""
    policy = _network_policy(network_policy)
    # Hide host processes: a shared /proc can otherwise expose their root
    # filesystem views through /proc/<pid>/root despite read-only mounts.
    argv = ["bwrap", "--die-with-parent", "--unshare-pid"]
    # Anonymous /tmp is private to this invocation, never the host's /tmp.
    argv.extend(["--tmpfs", "/tmp"])
    for path in _runtime_roots(project_root):
        argv.extend(["--ro-bind", str(path), str(path)])
    argv.extend(["--proc", "/proc", "--dev", "/dev"])
    for path in [workspace_path, *([output_path] if output_path is not None else [])]:
        argv.extend(["--bind", str(path), str(path)])
    argv.extend(["--chdir", str(cwd or workspace_path)])
    if policy == "none":
        argv.append("--unshare-net")
    argv.extend(["--", *inner_argv])
    return argv

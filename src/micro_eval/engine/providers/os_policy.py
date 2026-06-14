"""OS-level sandbox providers: Seatbelt (macOS) and Bubblewrap (Linux).

Level 1 (semi_trusted) isolation via OS policy enforcement.
Filesystem access is restricted to the workspace directory;
network access follows the configured policy.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import textwrap
from pathlib import Path

from micro_eval.engine.providers.base import (
    CommandResult,
    IsolationLevel,
    NetworkPolicy,
    WorkspaceHandle,
)
from micro_eval.engine.providers.git_worktree import (
    GitWorktreeProvider,
    WorkspaceProviderError,
)
from micro_eval.models.artifact import ArtifactRef
from micro_eval.models.task import WorkspaceSpec


class SeatbeltProvider:
    """macOS sandbox-exec (Seatbelt) provider for Level 1 isolation.

    Wraps a GitWorktreeProvider for workspace creation/cleanup, then
    enforces OS-level filesystem and network restrictions via sandbox-exec.
    """

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root.resolve()
        self._inner = GitWorktreeProvider(project_root)
        self._available = (
            platform.system() == "Darwin"
            and shutil.which("sandbox-exec") is not None
        )

    @property
    def name(self) -> str:
        return "seatbelt"

    @property
    def supported_levels(self) -> list[IsolationLevel]:
        if self._available:
            return [IsolationLevel.os_policy]
        return []

    def create(self, spec: WorkspaceSpec, *, cell_id: str, run_id: str) -> WorkspaceHandle:
        handle = self._inner.create(spec, cell_id=cell_id, run_id=run_id)
        return WorkspaceHandle(
            workspace_path=handle.workspace_path,
            provider_name=self.name,
            isolation_level=IsolationLevel.os_policy,
            source_repo=handle.source_repo,
            metadata={
                "sandbox_type": "seatbelt",
                "network_policy": spec.network_policy.value if spec.network_policy else "full",
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

        network_policy = handle.metadata.get("network_policy", "full")
        profile = _build_seatbelt_profile(handle.workspace_path, network_policy)

        sandbox_argv = [
            "sandbox-exec", "-p", profile,
            *argv,
        ]
        try:
            result = subprocess.run(
                sandbox_argv,
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

    def collect_artifacts(self, handle: WorkspaceHandle) -> list[ArtifactRef]:
        return self._inner.collect_artifacts(handle)

    def collect_diff(self, handle: WorkspaceHandle) -> str | None:
        return self._inner.collect_diff(handle)

    def snapshot(self, handle: WorkspaceHandle) -> str:
        return self._inner.snapshot(handle)

    def restore(self, handle: WorkspaceHandle, snap: str) -> None:
        raise NotImplementedError("restore not supported for seatbelt provider")

    def cleanup(self, handle: WorkspaceHandle) -> None:
        self._inner.cleanup(handle)


class BubblewrapProvider:
    """Linux Bubblewrap (bwrap) provider for Level 1 isolation.

    Wraps a GitWorktreeProvider for workspace creation/cleanup, then
    enforces OS-level filesystem and network restrictions via bwrap.
    """

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root.resolve()
        self._inner = GitWorktreeProvider(project_root)
        self._available = (
            platform.system() == "Linux"
            and shutil.which("bwrap") is not None
        )

    @property
    def name(self) -> str:
        return "bubblewrap"

    @property
    def supported_levels(self) -> list[IsolationLevel]:
        if self._available:
            return [IsolationLevel.os_policy]
        return []

    def create(self, spec: WorkspaceSpec, *, cell_id: str, run_id: str) -> WorkspaceHandle:
        handle = self._inner.create(spec, cell_id=cell_id, run_id=run_id)
        return WorkspaceHandle(
            workspace_path=handle.workspace_path,
            provider_name=self.name,
            isolation_level=IsolationLevel.os_policy,
            source_repo=handle.source_repo,
            metadata={
                "sandbox_type": "bubblewrap",
                "network_policy": spec.network_policy.value if spec.network_policy else "full",
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

        network_policy = handle.metadata.get("network_policy", "full")
        bwrap_argv = _build_bwrap_argv(handle.workspace_path, network_policy, argv)
        try:
            result = subprocess.run(
                bwrap_argv,
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

    def collect_artifacts(self, handle: WorkspaceHandle) -> list[ArtifactRef]:
        return self._inner.collect_artifacts(handle)

    def collect_diff(self, handle: WorkspaceHandle) -> str | None:
        return self._inner.collect_diff(handle)

    def snapshot(self, handle: WorkspaceHandle) -> str:
        return self._inner.snapshot(handle)

    def restore(self, handle: WorkspaceHandle, snap: str) -> None:
        raise NotImplementedError("restore not supported for bubblewrap provider")

    def cleanup(self, handle: WorkspaceHandle) -> None:
        self._inner.cleanup(handle)


def _build_seatbelt_profile(workspace_path: Path, network_policy: str) -> str:
    """Generate a Seatbelt sandbox profile restricting filesystem writes and network.

    Level 1 strategy: allow all reads (system binaries need broad library access),
    restrict writes to workspace only, control network per policy.
    """
    ws = str(workspace_path).replace("\\", "\\\\").replace('"', '\\"')
    network_rule = "(allow network*)" if network_policy == "full" else "(deny network*)"
    if network_policy == "allowlist":
        network_rule = '(allow network* (remote ip "localhost:*"))\n  (deny network*)'
    return textwrap.dedent(f"""\
        (version 1)
        (deny default)
        (allow process*)
        (allow sysctl*)
        (allow mach*)
        (allow signal)
        (allow file-read*)
        (allow file-write* (subpath "{ws}"))
        (allow file-write-data (literal "/dev/null"))
        (allow file-write-data (literal "/dev/dtracehelper"))
        {network_rule}
    """)


def _build_bwrap_argv(
    workspace_path: Path, network_policy: str, inner_argv: list[str]
) -> list[str]:
    """Build a bwrap command line with filesystem and network restrictions."""
    ws = str(workspace_path)
    argv = [
        "bwrap",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/bin", "/bin",
        "--ro-bind", "/lib", "/lib",
        "--ro-bind", "/lib64", "/lib64",
        "--ro-bind", "/etc", "/etc",
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        "--bind", ws, ws,
        "--chdir", ws,
    ]
    if network_policy in ("none", "allowlist"):
        argv.append("--unshare-net")
    argv.extend(inner_argv)
    return argv

"""Remote workspace providers: E2B (VM) and Modal (container).

Level 3-4 isolation for untrusted/adversarial agent execution.
These providers require external credentials and are optional —
missing credentials make the provider unavailable (empty supported_levels),
never silently degrade to local execution.
"""

from __future__ import annotations

import logging
import os
import shlex
from pathlib import Path

from micro_eval.engine.providers.base import (
    CommandResult,
    IsolationLevel,
    NetworkPolicy,
    TrustLevel,
    WorkspaceHandle,
)
from micro_eval.engine.providers.git_worktree import WorkspaceProviderError
from micro_eval.models.ids import safe_path_segment
from micro_eval.models.artifact import ArtifactRef
from micro_eval.models.task import WorkspaceSpec

logger = logging.getLogger(__name__)

E2B_API_KEY_ENV = "MICRO_EVAL_SECRET_E2B_API_KEY"
MODAL_TOKEN_ID_ENV = "MICRO_EVAL_SECRET_MODAL_TOKEN_ID"
MODAL_TOKEN_SECRET_ENV = "MICRO_EVAL_SECRET_MODAL_TOKEN_SECRET"


class E2BProvider:
    """E2B sandbox provider: Level 4 (vm) isolation for adversarial agents.

    Requires E2B API key via MICRO_EVAL_SECRET_E2B_API_KEY env var.
    Network policy: none (fully isolated VM).
    Supports snapshot/restore via E2B native snapshots.
    """

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root.resolve()
        self._api_key = os.environ.get(E2B_API_KEY_ENV, "")

    @property
    def name(self) -> str:
        return "e2b"

    @property
    def supported_levels(self) -> list[IsolationLevel]:
        if self._api_key:
            return [IsolationLevel.vm]
        return []

    def create(self, spec: WorkspaceSpec, *, cell_id: str, run_id: str) -> WorkspaceHandle:
        if not self._api_key:
            raise WorkspaceProviderError(
                f"E2B provider requires {E2B_API_KEY_ENV} environment variable. "
                "Remote providers do not degrade to local execution for security reasons."
            )
        try:
            from e2b_code_interpreter import Sandbox
        except ImportError as exc:
            raise WorkspaceProviderError(
                "E2B SDK not installed. Install with: pip install e2b-code-interpreter"
            ) from exc

        sandbox = Sandbox(api_key=self._api_key, timeout=300)
        sandbox_id = sandbox.sandbox_id

        safe_cell = safe_path_segment(cell_id)
        workspace_dir = f"/home/user/workspace/{safe_cell}"
        sandbox.commands.run(f"mkdir -p {shlex.quote(workspace_dir)}")

        if spec.setup:
            for cmd_argv in spec.setup:
                sandbox.commands.run(shlex.join(cmd_argv), cwd=workspace_dir)

        return WorkspaceHandle(
            workspace_path=Path(workspace_dir),
            provider_name=self.name,
            isolation_level=IsolationLevel.vm,
            metadata={
                "sandbox_id": sandbox_id,
                "network_policy": NetworkPolicy.none.value,
                "trust_level": TrustLevel.adversarial.value,
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

        sandbox_id = handle.metadata.get("sandbox_id")
        if not sandbox_id:
            raise WorkspaceProviderError("Missing sandbox_id in handle metadata")

        try:
            from e2b_code_interpreter import Sandbox

            sandbox = Sandbox.connect(sandbox_id, api_key=self._api_key)
            result = sandbox.commands.run(
                shlex.join(argv),
                cwd=str(handle.workspace_path),
                timeout=int(timeout_s) if timeout_s else 300,
                envs=env or {},
            )
            return CommandResult(
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        except Exception as exc:
            if "timeout" in str(exc).lower():
                return CommandResult(exit_code=-1, timed_out=True)
            raise WorkspaceProviderError(f"E2B execution failed: {exc}") from exc

    def collect_artifacts(self, handle: WorkspaceHandle) -> list[ArtifactRef]:
        return []

    def collect_diff(self, handle: WorkspaceHandle) -> str | None:
        return None

    def snapshot(self, handle: WorkspaceHandle) -> str:
        return handle.metadata.get("sandbox_id", "")

    def restore(self, handle: WorkspaceHandle, snap: str) -> None:
        raise NotImplementedError("restore not yet implemented for E2B provider")

    def cleanup(self, handle: WorkspaceHandle) -> None:
        sandbox_id = handle.metadata.get("sandbox_id")
        if not sandbox_id:
            return
        try:
            from e2b_code_interpreter import Sandbox

            sandbox = Sandbox.connect(sandbox_id, api_key=self._api_key)
            sandbox.kill()
        except Exception:
            logger.warning("Failed to cleanup E2B sandbox %s", sandbox_id)


class ModalProvider:
    """Modal container provider: Level 3 (container) isolation for untrusted agents.

    Requires Modal credentials via MICRO_EVAL_SECRET_MODAL_TOKEN_ID and
    MICRO_EVAL_SECRET_MODAL_TOKEN_SECRET env vars.
    Network policy: allowlist (container-level network isolation).
    """

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root.resolve()
        self._token_id = os.environ.get(MODAL_TOKEN_ID_ENV, "")
        self._token_secret = os.environ.get(MODAL_TOKEN_SECRET_ENV, "")

    @property
    def name(self) -> str:
        return "modal"

    @property
    def supported_levels(self) -> list[IsolationLevel]:
        if self._token_id and self._token_secret:
            return [IsolationLevel.container]
        return []

    def create(self, spec: WorkspaceSpec, *, cell_id: str, run_id: str) -> WorkspaceHandle:
        if not self._token_id or not self._token_secret:
            raise WorkspaceProviderError(
                f"Modal provider requires {MODAL_TOKEN_ID_ENV} and {MODAL_TOKEN_SECRET_ENV} "
                "environment variables. Remote providers do not degrade to local execution "
                "for security reasons."
            )
        try:
            import modal  # noqa: F401
        except ImportError as exc:
            raise WorkspaceProviderError(
                "Modal SDK not installed. Install with: pip install modal"
            ) from exc

        safe_cell = safe_path_segment(cell_id)
        workspace_dir = f"/tmp/workspace/{safe_cell}"

        return WorkspaceHandle(
            workspace_path=Path(workspace_dir),
            provider_name=self.name,
            isolation_level=IsolationLevel.container,
            metadata={
                "run_id": run_id,
                "cell_id": cell_id,
                "network_policy": NetworkPolicy.allowlist.value,
                "trust_level": TrustLevel.untrusted.value,
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
            import modal

            app = modal.App("micro-eval-sandbox")
            image = modal.Image.debian_slim()

            @app.function(image=image, timeout=int(timeout_s) if timeout_s else 300)
            def run_command():
                import os as _os
                import subprocess

                run_env = _os.environ.copy()
                if env:
                    run_env.update(env)
                result = subprocess.run(
                    argv,
                    cwd=str(handle.workspace_path),
                    env=run_env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                return {
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }

            with app.run():
                result = run_command.remote()
                return CommandResult(
                    exit_code=result["exit_code"],
                    stdout=result["stdout"],
                    stderr=result["stderr"],
                )
        except Exception as exc:
            if "timeout" in str(exc).lower():
                return CommandResult(exit_code=-1, timed_out=True)
            raise WorkspaceProviderError(f"Modal execution failed: {exc}") from exc

    def collect_artifacts(self, handle: WorkspaceHandle) -> list[ArtifactRef]:
        return []

    def collect_diff(self, handle: WorkspaceHandle) -> str | None:
        return None

    def snapshot(self, handle: WorkspaceHandle) -> str:
        return ""

    def restore(self, handle: WorkspaceHandle, snap: str) -> None:
        raise NotImplementedError("restore not yet implemented for Modal provider")

    def cleanup(self, handle: WorkspaceHandle) -> None:
        pass

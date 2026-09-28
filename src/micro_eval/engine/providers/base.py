"""WorkspaceProvider Protocol and shared types for isolation backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from micro_eval.models.environment import WorkspaceObservation
from micro_eval.models.task import IsolationLevel, NetworkPolicy, TrustLevel, WorkspaceType


@dataclass
class WorkspaceHandle:
    """Opaque handle returned by a provider after workspace creation."""

    workspace_path: Path
    provider_name: str
    isolation_level: IsolationLevel
    metadata: dict[str, str] = field(default_factory=dict)
    source_repo: Path | None = None
    workspace_type: WorkspaceType = WorkspaceType.blank
    setup_exit_code: int | None = None
    is_remote: bool = False


@dataclass(frozen=True)
class ExecutionRequest:
    """An argv invocation expressed entirely in the execution filesystem."""

    argv: list[str]
    cwd: Path | None = None
    env: dict[str, str] | None = None
    stdin: bytes | None = None
    timeout_s: float | None = None
    output_cap_bytes: int = 10 * 1024 * 1024


@dataclass
class CommandResult:
    """Result of executing a command in a workspace."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False


@runtime_checkable
class WorkspaceProvider(Protocol):
    """Protocol for workspace isolation backends (spec §3.4.4).

    Cell execution is asynchronous and cancellation must terminate the owned
    process or sandbox before propagating cancellation. The synchronous
    exec_command method remains a compatibility entry point only.
    """

    @property
    def name(self) -> str: ...

    @property
    def supported_levels(self) -> list[IsolationLevel]: ...

    def create(self, spec: "WorkspaceSpec", *, cell_id: str, run_id: str) -> WorkspaceHandle: ...

    async def execute(self, handle: WorkspaceHandle, request: ExecutionRequest) -> CommandResult: ...

    def exec_command(
        self,
        handle: WorkspaceHandle,
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> CommandResult: ...

    def observe_final(
        self,
        handle: WorkspaceHandle,
        *,
        byte_limit: int,
    ) -> WorkspaceObservation: ...

    def snapshot(self, handle: WorkspaceHandle) -> str: ...

    def restore(self, handle: WorkspaceHandle, snap: str) -> None: ...

    def cleanup(self, handle: WorkspaceHandle) -> None: ...


# Import after Protocol definition to break circular import cycle
# between providers/base.py and models/task.py (runtime import).
from micro_eval.models.task import WorkspaceSpec  # noqa: E402


class ProviderRegistry:
    """Registry that selects providers by isolation level."""

    def __init__(self) -> None:
        self._providers: list[WorkspaceProvider] = []

    def register(self, provider: WorkspaceProvider) -> None:
        self._providers.append(provider)

    def select(self, level: IsolationLevel) -> WorkspaceProvider | None:
        for provider in self._providers:
            if level in provider.supported_levels:
                return provider
        return None

    @property
    def providers(self) -> list[WorkspaceProvider]:
        return list(self._providers)

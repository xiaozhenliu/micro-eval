"""WorkspaceProvider Protocol and shared types for isolation backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from micro_eval.models.artifact import ArtifactRef
from micro_eval.models.task import IsolationLevel, NetworkPolicy, TrustLevel


@dataclass
class WorkspaceHandle:
    """Opaque handle returned by a provider after workspace creation."""

    workspace_path: Path
    provider_name: str
    isolation_level: IsolationLevel
    metadata: dict[str, str] = field(default_factory=dict)
    source_repo: Path | None = None


@dataclass
class CommandResult:
    """Result of executing a command in a workspace."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


@runtime_checkable
class WorkspaceProvider(Protocol):
    """Protocol for workspace isolation backends (spec §3.4.4).

    Methods are synchronous for Level 0/1 providers (local operations).
    Remote providers (P3-c) will introduce an AsyncWorkspaceProvider variant.
    """

    @property
    def name(self) -> str: ...

    @property
    def supported_levels(self) -> list[IsolationLevel]: ...

    def create(self, spec: "WorkspaceSpec", *, cell_id: str, run_id: str) -> WorkspaceHandle: ...

    def exec_command(
        self,
        handle: WorkspaceHandle,
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> CommandResult: ...

    def collect_artifacts(self, handle: WorkspaceHandle) -> list[ArtifactRef]: ...

    def collect_diff(self, handle: WorkspaceHandle) -> str | None: ...

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

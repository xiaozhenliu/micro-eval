"""Workspace providers: pluggable isolation backends for agent execution."""

from micro_eval.engine.providers.base import (
    CommandResult,
    IsolationLevel,
    NetworkPolicy,
    ProviderRegistry,
    TrustLevel,
    WorkspaceHandle,
    WorkspaceProvider,
)
from micro_eval.engine.providers.git_worktree import GitWorktreeProvider
from micro_eval.engine.providers.os_policy import BubblewrapProvider, SeatbeltProvider
from micro_eval.engine.providers.remote import E2BProvider, ModalProvider

__all__ = [
    "BubblewrapProvider",
    "CommandResult",
    "E2BProvider",
    "GitWorktreeProvider",
    "IsolationLevel",
    "ModalProvider",
    "NetworkPolicy",
    "ProviderRegistry",
    "SeatbeltProvider",
    "TrustLevel",
    "WorkspaceHandle",
    "WorkspaceProvider",
]

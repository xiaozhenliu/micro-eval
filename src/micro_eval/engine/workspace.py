"""Workspace isolation via git worktree."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Optional


class WorkspaceError(Exception):
    """Raised when workspace operations fail."""
    pass


class WorkspaceManager:
    """Manages isolated workspaces using git worktree."""

    def __init__(self, repo_root: Path | str):
        self.repo_root = Path(repo_root)
        self._worktrees: list[Path] = []

    def create(self, suffix: str = "eval") -> Path:
        """Create a new git worktree for isolated execution."""
        if not (self.repo_root / ".git").exists():
            # Not a git repo - fall back to temp directory
            tmp = Path(tempfile.mkdtemp(prefix=f"micro-eval-{suffix}-"))
            self._worktrees.append(tmp)
            return tmp

        # Get current commit
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
            commit = result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise WorkspaceError(f"Failed to get HEAD: {e.stderr}")

        # Create worktree in temp location
        worktree_path = Path(
            tempfile.mkdtemp(prefix=f"micro-eval-{suffix}-")
        )
        # Remove the temp dir so git worktree add can create it
        worktree_path.rmdir()

        try:
            subprocess.run(
                ["git", "worktree", "add", "--detach",
                 str(worktree_path), commit],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise WorkspaceError(f"Failed to create worktree: {e.stderr}")

        self._worktrees.append(worktree_path)
        return worktree_path

    def collect_diff(self, worktree_path: Path) -> Optional[str]:
        """Collect git diff from a worktree (uncommitted changes)."""
        try:
            result = subprocess.run(
                ["git", "diff", "--no-color"],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout if result.stdout.strip() else None
        except subprocess.CalledProcessError:
            return None

    def cleanup(self) -> None:
        """Remove all created worktrees."""
        import shutil
        for wt in self._worktrees:
            if not wt.exists():
                continue
            # Try git worktree remove first
            try:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(wt)],
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                    check=True,
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Fall back to rm
                shutil.rmtree(wt, ignore_errors=True)
        self._worktrees.clear()

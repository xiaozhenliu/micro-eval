"""Judge a code-fix task from outside the agent-writable workspace.

Starter tasks copy a small module plus a ``tests/`` suite into the cell
workspace. The agent is allowed to change the module; it must not change the
tests. Putting the judge script inside the workspace (``tools/verify.py``)
does not work: the agent can edit the judge as easily as the tests. This
module lives in the installed ``micro_eval`` package instead, and the task's
validator expectation invokes it with the expected digest of the protected
directory, which is stored in the task YAML outside the workspace::

    expectations:
      - type: command
        command: ["{python}", "-m", "micro_eval.tools.verify_protected",
                  "--protected-dir", "tests", "--expected-sha256", "<hex>"]
        cwd: "<fixture dir>"

How a run works:

1. Digest the protected directory (names, sizes, bytes; symlinks rejected)
   and compare with the expected value. Mismatch → exit 2.
2. Copy the protected directory to a fresh, read-only snapshot under the
   system temp directory and run ``unittest discover`` from *that* copy, with
   the fixture root as the working directory so the module under test is
   importable. The workspace copy is never what runs.
3. Digest the workspace copy again after the run. Any change → exit 2, even
   if the tests passed.

Limits (state them, do not paper over them): the tests and the module under
test execute in one Python process. Code that runs at import time can still
monkeypatch ``unittest`` or edit files it manages to locate, including the
snapshot. The digest gate defeats the cheap moves (editing or adding test
files before or during the run); it is not process isolation. Treat a pass
as "protected tests unchanged and green", keep the persisted workspace diff
as the audit trail, and use a sandboxed workspace provider for adversarial
agents.

Usage (from the fixture directory, i.e. the validator's cwd)::

    python -m micro_eval.tools.verify_protected --protected-dir tests --expected-sha256 <hex>
    python -m micro_eval.tools.verify_protected --protected-dir tests --print-digest
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

SKIP_DIR_NAMES = frozenset({"__pycache__"})
SKIP_SUFFIXES = frozenset({".pyc", ".pyo"})

EXIT_TAMPERED = 2
EXIT_USAGE = 3


def compute_protected_digest(root: Path | str) -> str:
    """Return a sha256 hex digest over every file under ``root``.

    The digest covers the sorted relative POSIX path, the byte length, and the
    bytes of each regular file. Bytecode caches are ignored. Any symlink under
    ``root`` (file or directory) raises ``ValueError`` so a swapped-in link can
    never produce a matching digest.
    """
    root_path = Path(root)
    if root_path.is_symlink() or not root_path.is_dir():
        raise ValueError("protected directory must be a real directory")

    entries: list[tuple[str, bytes]] = []
    for dirpath, dirnames, filenames in os.walk(root_path, followlinks=False):
        current = Path(dirpath)
        kept: list[str] = []
        for name in sorted(dirnames):
            child = current / name
            if child.is_symlink():
                raise ValueError(f"symlink inside protected directory: {child.relative_to(root_path).as_posix()}")
            if name in SKIP_DIR_NAMES:
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            child = current / name
            if child.is_symlink():
                raise ValueError(f"symlink inside protected directory: {child.relative_to(root_path).as_posix()}")
            if child.suffix in SKIP_SUFFIXES:
                continue
            entries.append((child.relative_to(root_path).as_posix(), child.read_bytes()))

    digest = hashlib.sha256()
    for rel, data in sorted(entries):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(data)).encode("ascii"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return digest.hexdigest()


def _ignore_caches(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in SKIP_DIR_NAMES or Path(name).suffix in SKIP_SUFFIXES}


_RO_FILE = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
_RO_DIR = stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH


def _is_symlink(path: Path) -> bool:
    try:
        return stat.S_ISLNK(os.lstat(path).st_mode)
    except OSError:
        return False


def snapshot_protected_dir(protected: Path, expected_digest: str) -> Path:
    """Copy ``protected`` into a fresh temp directory, verify the copy, and
    make it read-only.

    Symlinks are copied as links (never dereferenced) and the copy is
    digested again: a link slipped in between the first digest and the copy
    makes the snapshot digest fail, so the tests never run against it. On any
    failure the temp directory is removed before the error propagates.
    Returns the snapshot root; the protected copy is ``<root>/<name>``.
    """
    root = Path(tempfile.mkdtemp(prefix="micro-eval-protected-"))
    try:
        target = root / protected.name
        shutil.copytree(protected, target, symlinks=True, ignore=_ignore_caches)
        if compute_protected_digest(target) != expected_digest:
            raise ValueError("protected directory changed while it was being copied")
        for dirpath, dirnames, filenames in os.walk(target, followlinks=False):
            for name in filenames:
                child = Path(dirpath) / name
                if not _is_symlink(child):
                    os.chmod(child, _RO_FILE)
            for name in dirnames:
                child = Path(dirpath) / name
                if not _is_symlink(child):
                    os.chmod(child, _RO_DIR)
        os.chmod(target, _RO_DIR)
        return root
    except BaseException:
        _remove_snapshot(root)
        raise


def _remove_snapshot(root: Path) -> None:
    """Delete the snapshot. Only directories need write permission restored
    (POSIX unlink needs a writable parent, not a writable file); symlinks
    are never chmod'ed, so nothing outside the snapshot is touched."""
    for dirpath, dirnames, _filenames in os.walk(root, followlinks=False):
        if not _is_symlink(Path(dirpath)):
            os.chmod(dirpath, stat.S_IRWXU)
        for name in dirnames:
            child = Path(dirpath) / name
            if not _is_symlink(child):
                os.chmod(child, stat.S_IRWXU)
    shutil.rmtree(root, ignore_errors=True)


def run_unittest(start_dir: Path, cwd: Path) -> int:
    """Run ``unittest discover`` (argv-only) from ``start_dir`` with ``cwd`` on sys.path.

    The suite runs in its own session so that, when the validator times out
    and terminates this judge, the judge can take the whole test process
    group down with it instead of leaving tests running.
    """
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    child = subprocess.Popen(
        [sys.executable, "-m", "unittest", "discover", "-s", str(start_dir), "-t", str(start_dir), "-v"],
        cwd=str(cwd),
        env=env,
        start_new_session=True,
    )

    def _forward(signum: int, _frame: object) -> None:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        raise SystemExit(128 + signum)

    previous = {sig: signal.signal(sig, _forward) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    try:
        return child.wait()
    except BaseException:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        raise
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m micro_eval.tools.verify_protected",
        description="Verify a protected test directory is unchanged, run its unittest suite from a read-only snapshot, and re-verify afterwards.",
    )
    parser.add_argument("--protected-dir", default="tests", help="Directory that must be unchanged (relative to --root)")
    parser.add_argument("--expected-sha256", default=None, help="Digest produced earlier by --print-digest")
    parser.add_argument("--print-digest", action="store_true", help="Print the current digest and exit")
    parser.add_argument("--root", default=".", help="Fixture root (default: current directory)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    protected = root / args.protected_dir
    try:
        before = compute_protected_digest(protected)
    except (OSError, ValueError) as exc:
        print(f"verify_protected: cannot digest '{args.protected_dir}': {exc}", file=sys.stderr)
        return EXIT_TAMPERED

    if args.print_digest:
        print(before)
        return 0

    if not args.expected_sha256:
        print("verify_protected: --expected-sha256 is required (or use --print-digest)", file=sys.stderr)
        return EXIT_USAGE

    expected = args.expected_sha256.strip().lower()
    if before != expected:
        print(
            f"verify_protected: '{args.protected_dir}' was modified; restore it and fix the module "
            "under test instead of editing the tests.",
            file=sys.stderr,
        )
        return EXIT_TAMPERED

    try:
        snapshot_root = snapshot_protected_dir(protected, expected)
    except (OSError, ValueError) as exc:
        print(f"verify_protected: cannot snapshot '{args.protected_dir}': {exc}", file=sys.stderr)
        return EXIT_TAMPERED
    try:
        returncode = run_unittest(snapshot_root / protected.name, root)
    finally:
        _remove_snapshot(snapshot_root)

    try:
        after = compute_protected_digest(protected)
    except (OSError, ValueError) as exc:
        print(f"verify_protected: '{args.protected_dir}' changed during the run: {exc}", file=sys.stderr)
        return EXIT_TAMPERED
    if after != expected:
        print(
            f"verify_protected: '{args.protected_dir}' was modified while the tests ran; result rejected.",
            file=sys.stderr,
        )
        return EXIT_TAMPERED

    return returncode


if __name__ == "__main__":
    raise SystemExit(main())

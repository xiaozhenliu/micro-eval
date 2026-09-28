"""Pure helpers for reading and editing eval.yaml and task files.

This module has no typer/CLI concerns; `micro_eval.cli.config_cmd` is a thin
wrapper that turns exceptions raised here into JSON error output. Keeping the
logic here makes it independently unit-testable and reusable from
`scripts/generate-golden.py` (GRO-549).

Security notes (docs/engineering/security-development-guidelines.md):
- No subprocess calls happen in this module; it only reads/writes local files.
- Every file access walks from the resolved project directory one path
  component at a time with ``O_DIRECTORY | O_NOFOLLOW`` and a directory fd,
  then opens the final name with ``O_NOFOLLOW`` and checks the open fd
  (regular file, single hard link). Writes create an ``O_EXCL`` temp file in
  that directory and ``rename`` it into place through the same fd, so a
  concurrent swap of any path component to a symlink cannot redirect a read,
  a write, or a delete outside the project (F3/F4 of the 2026-09-12 review).
- Relative task paths are validated before they are used or echoed back.
- Error messages must never contain absolute paths.
- Secrets never enter eval.yaml through this module: ``MICRO_EVAL_SECRET_*``
  names are rejected as ``agent.env`` keys, values equal to a declared secret
  are rejected, and ``config show`` redacts declared secret values.
"""

from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone
import re
import stat as stat_module
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from pydantic import ValidationError

from micro_eval.config.loader import ConfigError, _parse_task
from micro_eval.engine.adapter import Redactor
from micro_eval.models.configuration import SAFE_ID_RE, ConfigurationSpec
from micro_eval.models.task import TaskSpec

SECRET_ENV_PREFIX = "MICRO_EVAL_SECRET_"
REDACTION_MARKER = "[REDACTED"

VALIDATION = "validation"
NOT_FOUND = "not_found"
INTERNAL = "internal"
CONFLICT = "conflict"


class ConfigEditError(Exception):
    """Raised for editor-level validation/safety errors.

    Messages must be safe to show to a caller (e.g. the UI): no absolute
    paths, no server directory structure. ``kind`` lets the CLI/API map the
    error to a status (validation → 400, not_found → 404, internal → 502).
    """

    kind: str = VALIDATION

    def __init__(self, message: str, *, kind: str | None = None):
        super().__init__(message)
        if kind is not None:
            self.kind = kind


class ConfigNotFoundError(ConfigEditError):
    kind = NOT_FOUND


# ---------------------------------------------------------------------------
# Id / path validation
# ---------------------------------------------------------------------------


def is_safe_id(value: Any) -> bool:
    """Path-safe id that is not composed only of dots (``.``/``..``)."""
    if not isinstance(value, str) or not SAFE_ID_RE.fullmatch(value):
        return False
    return set(value) != {"."}


_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def validate_relative_path(raw: Any, *, allow_runtime_dir: bool = False) -> PurePosixPath:
    """Validate a project-relative POSIX path from eval.yaml or a caller.

    Rejects non-strings, empty strings, absolute paths, Windows drive
    prefixes, backslashes, NUL/control characters, and ``.``/``..`` segments.
    The ``.micro-eval`` runtime directory (locks, audit log, runs) is
    reserved: only ``output_dir`` may point into it (round-13 review).
    """
    if not isinstance(raw, str) or raw == "":
        raise ConfigEditError("path must be a non-empty string")
    if "\x00" in raw or "\\" in raw:
        raise ConfigEditError("path contains an unsupported character")
    if raw.startswith("/") or _WINDOWS_DRIVE_RE.match(raw):
        raise ConfigEditError("path must be relative to the project")
    # Split the raw string: PurePosixPath drops "." segments and collapses
    # "//", which would hide exactly the segments we want to reject.
    segments = raw.split("/")
    for segment in segments:
        if segment in ("", ".", ".."):
            raise ConfigEditError("path must not contain empty, '.' or '..' segments")
        if any(ord(char) < 32 for char in segment):
            raise ConfigEditError("path contains control characters")
    if segments[0] == RUNTIME_DIR and not allow_runtime_dir:
        raise ConfigEditError("path must not point into the .micro-eval runtime directory")
    return PurePosixPath(*segments)


# ---------------------------------------------------------------------------
# Error formatting (never echo user input or absolute paths)
# ---------------------------------------------------------------------------


def format_validation_error(exc: ValidationError) -> str:
    """Render a pydantic error as ``loc: message`` pairs without input values."""
    parts = []
    for item in exc.errors(include_url=False, include_input=False):
        loc = ".".join(str(piece) for piece in item.get("loc", ())) or "<root>"
        parts.append(f"{loc}: {item.get('msg', 'invalid value')}")
    return "; ".join(parts) or "validation error"


def _sanitize_message(message: str, project_dir: Path) -> str:
    project_str = str(project_dir)
    sanitized = message.replace(project_str + os.sep, "")
    return sanitized.replace(project_str, ".")


# ---------------------------------------------------------------------------
# fd-based file access (symlink / hardlink / TOCTOU safe)
# ---------------------------------------------------------------------------


def _require_dir_fd_support() -> None:
    # os.stat(..., follow_symlinks=False) stands in for lstat with dir_fd.
    needed = (os.open, os.rename, os.unlink, os.stat, os.mkdir)
    if any(fn not in os.supports_dir_fd for fn in needed):
        raise ConfigEditError("safe file access is not supported on this platform", kind=INTERNAL)


def resolve_project_dir(project: str | Path) -> Path:
    """Resolve and validate the project root directory."""
    path = Path(project)
    try:
        resolved = path.resolve(strict=False)
    except OSError as exc:
        raise ConfigEditError("invalid project path") from exc
    if not resolved.exists():
        raise ConfigEditError("project directory does not exist")
    if not resolved.is_dir():
        raise ConfigEditError("project path is not a directory")
    return resolved


def _open_dir_chain(project_dir: Path, parts: tuple[str, ...], *, create: bool) -> int:
    """Open ``project_dir/parts...`` one component at a time, refusing symlinks.

    Returns an fd for the final directory; the caller must close it.
    """
    _require_dir_fd_support()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        fd = os.open(str(project_dir), flags)
    except OSError as exc:
        raise ConfigEditError("project directory cannot be opened") from exc
    try:
        for part in parts:
            try:
                next_fd = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise ConfigNotFoundError("directory not found") from None
                try:
                    os.mkdir(part, 0o755, dir_fd=fd)
                except FileExistsError:
                    pass  # a concurrent writer created it first; fall through to open it
                next_fd = os.open(part, flags, dir_fd=fd)
            except NotADirectoryError as exc:
                raise ConfigEditError("path component is not a directory") from exc
            except OSError as exc:
                # ELOOP (symlink under O_NOFOLLOW) or permission problems.
                raise ConfigEditError("path component is a symlink or cannot be opened") from exc
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _split(rel: PurePosixPath) -> tuple[tuple[str, ...], str]:
    parts = rel.parts
    return parts[:-1], parts[-1]


def _check_regular_single_link(st: os.stat_result, what: str) -> None:
    if stat_module.S_ISLNK(st.st_mode):
        raise ConfigEditError(f"{what} must not be a symlink")
    if not stat_module.S_ISREG(st.st_mode):
        raise ConfigEditError(f"{what} is not a regular file")
    if st.st_nlink != 1:
        # >1: another name reaches the same inode; 0: unlinked after open.
        raise ConfigEditError(f"{what} must have exactly one hard link")


def read_project_file(project_dir: Path, rel: PurePosixPath) -> bytes:
    """Read a project-relative file without following any symlink."""
    dirs, name = _split(rel)
    dfd = _open_dir_chain(project_dir, dirs, create=False)
    try:
        try:
            # O_NONBLOCK: a FIFO must not block the open; the fstat below rejects it.
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
        except FileNotFoundError:
            raise ConfigNotFoundError("file not found") from None
        except IsADirectoryError as exc:
            raise ConfigEditError("path is a directory") from exc
        except OSError as exc:
            raise ConfigEditError("path is a symlink or cannot be opened") from exc
    finally:
        os.close(dfd)
    try:
        _check_regular_single_link(os.fstat(fd), "file")
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            return handle.read()
    except OSError as exc:
        raise ConfigEditError("file cannot be read") from exc
    finally:
        if fd != -1:
            os.close(fd)


def write_project_file(project_dir: Path, rel: PurePosixPath, content: str) -> None:
    """Atomically write ``content`` to a project-relative path.

    Creates missing directories (refusing symlinked components), writes an
    ``O_EXCL`` temp file in the target directory, and renames it into place
    through the directory fd. An existing target must be a plain regular file
    with a single hard link.
    """
    dirs, name = _split(rel)
    dfd = _open_dir_chain(project_dir, dirs, create=True)
    try:
        try:
            existing = os.stat(name, dir_fd=dfd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            _check_regular_single_link(existing, "target file")
        tmp_name = f".{name}.tmp-{uuid.uuid4().hex[:12]}"
        fd = os.open(tmp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dfd)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
            os.rename(tmp_name, name, src_dir_fd=dfd, dst_dir_fd=dfd)
        except BaseException:
            try:
                os.unlink(tmp_name, dir_fd=dfd)
            except OSError:
                pass
            raise
    except ConfigEditError:
        raise
    except OSError as exc:
        raise ConfigEditError("file cannot be written") from exc
    finally:
        os.close(dfd)


def delete_project_file(project_dir: Path, rel: PurePosixPath) -> None:
    """Delete a project-relative regular file without following symlinks."""
    dirs, name = _split(rel)
    dfd = _open_dir_chain(project_dir, dirs, create=False)
    try:
        try:
            st = os.stat(name, dir_fd=dfd, follow_symlinks=False)
        except FileNotFoundError:
            raise ConfigNotFoundError("file not found") from None
        _check_regular_single_link(st, "file")
        os.unlink(name, dir_fd=dfd)
    except ConfigEditError:
        raise
    except OSError as exc:
        raise ConfigEditError("file cannot be deleted") from exc
    finally:
        os.close(dfd)


def list_yaml_files(project_dir: Path, rel_dir: PurePosixPath) -> list[str]:
    """Names of regular ``*.yaml`` files directly inside a project directory."""
    try:
        dfd = _open_dir_chain(project_dir, rel_dir.parts, create=False)
    except ConfigNotFoundError:
        return []
    try:
        names = []
        for name in os.listdir(dfd):
            if not name.endswith(".yaml") or name.startswith("."):
                continue
            try:
                st = os.stat(name, dir_fd=dfd, follow_symlinks=False)
            except OSError:
                continue
            if stat_module.S_ISREG(st.st_mode) and st.st_nlink == 1:
                names.append(name)
        return sorted(names)
    except OSError:
        return []
    finally:
        os.close(dfd)


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------


def strip_schema_version(value: Any) -> Any:
    """Recursively drop ``schema_version`` keys so dumped YAML/JSON matches
    the canonical hand-authored style (see eval.yaml.example)."""
    if isinstance(value, dict):
        return {key: strip_schema_version(val) for key, val in value.items() if key != "schema_version"}
    if isinstance(value, list):
        return [strip_schema_version(item) for item in value]
    return value


class _LiteralDumper(yaml.SafeDumper):
    """SafeDumper subclass so the string representer never leaks into the
    global yaml.SafeDumper used elsewhere in the process."""


def _represent_str(dumper: yaml.Dumper, data: str) -> yaml.Node:
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_LiteralDumper.add_representer(str, _represent_str)


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.dump(data, Dumper=_LiteralDumper, sort_keys=False, allow_unicode=True)


def _decode_text(data: bytes, what: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigEditError(f"{what} is not valid UTF-8") from exc


def _yaml_mapping_from_text(text: str, what: str) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigEditError(f"{what} is not valid YAML") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ConfigEditError(f"{what} must be a YAML mapping")
    return loaded


def _decode_yaml_mapping(data: bytes, what: str) -> dict[str, Any]:
    return _yaml_mapping_from_text(_decode_text(data, what), what)


EVAL_YAML = PurePosixPath("eval.yaml")
RUNTIME_DIR = ".micro-eval"
LOCK_FILE = "config.lock"
MAX_RAW_BYTES = 1024 * 1024
AUDIT_FILE = "config-audit.jsonl"
DRAFT_SCHEMA_VERSION = "1.0"


@contextmanager
def project_lock(project_dir: Path) -> Iterator[None]:
    """Serialise read-modify-write edits of one project across processes.

    Every CLI invocation is a separate process; two members saving at the
    same time would otherwise race on eval.yaml and one edit would vanish.
    The lock file lives in ``.micro-eval/`` (the runtime directory, already
    git-ignored) and is opened through the directory fd with ``O_NOFOLLOW``
    like everything else.
    """
    # flock is per open file description, so threads of one process must
    # additionally serialise on an in-process lock; it also removes the
    # create-race between concurrent first-time openers of the lock file.
    with _PROCESS_LOCK:
        dfd = _open_dir_chain(project_dir, (RUNTIME_DIR,), create=True)
        try:
            fd = _open_lock_file(dfd)
        finally:
            os.close(dfd)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


_PROCESS_LOCK = threading.Lock()


def _open_lock_file(dfd: int) -> int:
    """Open (creating if needed) the lock file below ``dfd``.

    Two processes creating the file at the same moment can see a transient
    ENOENT/EEXIST from ``openat(O_CREAT)``; retry briefly before giving up.
    """
    last: OSError | None = None
    for _ in range(5):
        try:
            return os.open(LOCK_FILE, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=dfd)
        except (FileNotFoundError, FileExistsError) as exc:
            last = exc
            time.sleep(0.01)
        except OSError as exc:
            raise ConfigEditError("project lock cannot be opened", kind=INTERNAL) from exc
    raise ConfigEditError("project lock cannot be opened", kind=INTERNAL) from last


def _is_legacy_layout(raw: Mapping[str, Any]) -> bool:
    """The loader still accepts the pre-canonical ``baseline``/``candidate``
    layout; the editor must not silently shadow it with ``configurations[]``."""
    return "configurations" not in raw and ("baseline" in raw or "candidate" in raw)


def _reject_legacy_layout(raw: Mapping[str, Any]) -> None:
    if _is_legacy_layout(raw):
        raise ConfigEditError(
            "eval.yaml uses the legacy baseline/candidate layout; convert it to configurations[] "
            "in the Advanced tab before editing with the forms"
        )


def load_raw_eval_yaml(project_dir: Path) -> dict[str, Any]:
    """Load eval.yaml as a plain dict for write operations (strict).

    Returns ``{}`` when the file does not exist (a blank project).
    """
    try:
        data = read_project_file(project_dir, EVAL_YAML)
    except ConfigNotFoundError:
        return {}
    return _decode_yaml_mapping(data, "eval.yaml")


def _write_eval_yaml(project_dir: Path, data: dict[str, Any]) -> None:
    write_project_file(project_dir, EVAL_YAML, dump_yaml(data))


# ---------------------------------------------------------------------------
# Task discovery (mirrors micro_eval.config.loader.load_task_paths)
# ---------------------------------------------------------------------------


def _tasks_dir(raw: dict[str, Any]) -> PurePosixPath:
    """``tasks_dir`` as the loader sees it: absent → ``tasks``; present but
    not a string (including ``null``) is invalid, exactly like the loader."""
    if "tasks_dir" not in raw:
        return PurePosixPath("tasks")
    value = raw.get("tasks_dir")
    if not isinstance(value, str):
        raise ConfigEditError("tasks_dir must be a string")
    return validate_relative_path(value)


def _explicit_task_list(raw: dict[str, Any]) -> list[Any] | None:
    """The explicit ``tasks:`` list when it is non-empty, else ``None``.

    The loader treats an empty list exactly like a missing key (it falls back
    to globbing ``tasks_dir``), so the editor must too, or the UI would show a
    different task set than ``micro-eval run`` executes.
    """
    if "tasks" not in raw:
        return None
    field = raw["tasks"]
    if not isinstance(field, list):
        # Includes an explicit ``tasks: null`` — the loader refuses it too.
        raise ConfigEditError("tasks must be a list of task paths")
    if isinstance(field, list) and field:
        return list(field)
    return None


class _DiscoveredTask:
    __slots__ = ("display", "error", "rel")

    def __init__(self, rel: PurePosixPath | None, display: str, error: str | None):
        self.rel = rel
        self.display = display
        self.error = error


def _discover_tasks(project_dir: Path, raw: dict[str, Any], warnings: list[str]) -> list[_DiscoveredTask]:
    found: list[_DiscoveredTask] = []
    try:
        explicit = _explicit_task_list(raw)
    except ConfigEditError as exc:
        # Same rule as the loader (which refuses to build a plan): surface it
        # as an invalid entry so the setup gate blocks Enqueue.
        found.append(_DiscoveredTask(None, "<invalid tasks field>", str(exc)))
        return found
    if explicit is not None:
        for index, item in enumerate(explicit):
            try:
                rel = validate_relative_path(item)
            except ConfigEditError as exc:
                found.append(_DiscoveredTask(None, f"<invalid tasks entry {index}>", str(exc)))
                continue
            found.append(_DiscoveredTask(rel, rel.as_posix(), None))
        return found

    try:
        tasks_dir = _tasks_dir(raw)
        names = list_yaml_files(project_dir, tasks_dir)
    except ConfigEditError as exc:
        warnings.append(f"tasks_dir ignored: {exc}")
        return found
    for name in names:
        rel = tasks_dir / name
        found.append(_DiscoveredTask(rel, rel.as_posix(), None))
    return found


def _load_task_spec(project_dir: Path, rel: PurePosixPath) -> TaskSpec:
    """Parse one task file from bytes read through the fd-safe path.

    The already-read text is handed to the loader for the revision digest so
    the file is never re-opened by path (which would reintroduce a
    symlink/TOCTOU window).
    """
    text = _decode_text(read_project_file(project_dir, rel), "task file")
    raw = _yaml_mapping_from_text(text, "task file")
    try:
        return _parse_task(raw, project_dir / Path(*rel.parts), source_text=text)
    except ValidationError as exc:
        raise ConfigEditError(format_validation_error(exc)) from exc
    except (ConfigError, TypeError, ValueError) as exc:
        raise ConfigEditError(_sanitize_message(str(exc), project_dir)) from exc


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


def declared_secrets(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """``MICRO_EVAL_SECRET_*`` names → non-empty values from the process env."""
    source = env if env is not None else os.environ
    return {key: value for key, value in source.items() if key.startswith(SECRET_ENV_PREFIX) and value}


def redact_scalar(value: str, secrets: Mapping[str, str]) -> str:
    """Mask declared secret values inside one string.

    A value that *equals* a declared secret becomes exactly the placeholder;
    otherwise every occurrence of every declared secret is replaced,
    whatever its length (longest secrets first).
    """
    for name, secret in secrets.items():
        if value == secret:
            return f"[REDACTED:{name}]"
    redacted = value
    # Substring replacement at any length: a declared secret is a declared
    # secret, and over-replacement only affects what the UI displays.
    for name, secret in sorted(secrets.items(), key=lambda item: -len(item[1])):
        redacted = redacted.replace(secret, f"[REDACTED:{name}]")
    return redacted


def redact_value(value: Any, secrets: Mapping[str, str]) -> Any:
    """Recursively mask declared secrets in every string of a JSON-like value.

    Applied to the whole ``config show`` draft: a secret pasted into an
    agent command, a task prompt, or a rubric must not reach the UI either.
    """
    if not secrets:
        return value
    if isinstance(value, str):
        return redact_scalar(value, secrets)
    if isinstance(value, dict):
        return {
            (redact_scalar(key, secrets) if isinstance(key, str) else key): redact_value(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item, secrets) for item in value]
    return value


def redact_env(env: dict[str, str], secrets: Mapping[str, str]) -> dict[str, str]:
    """Mask declared secret values (and any ``MICRO_EVAL_SECRET_*`` key) in an env mapping."""
    masked: dict[str, str] = {}
    for key, value in env.items():
        if key.startswith(SECRET_ENV_PREFIX):
            masked[key] = f"[REDACTED:{key}]"
        else:
            masked[key] = redact_scalar(value, secrets)
    return masked


def redact_text(text: str, secrets: Mapping[str, str]) -> tuple[str, bool]:
    """Replace declared secret values inside free text (raw eval.yaml)."""
    redacted = redact_scalar(text, secrets) if secrets else text
    return redacted, redacted != text


def _contains_placeholder(value: Any) -> bool:
    """True if any string inside a JSON-like value carries the redaction marker."""
    return any(REDACTION_MARKER in item for item in _iter_strings(value))


def _reject_secret_env(env: dict[str, str], preserved_keys: frozenset[str] = frozenset()) -> None:
    """Refuse secrets in ``agent.env``.

    ``preserved_keys`` are entries carried over unchanged from the stored
    configuration (the form showed them redacted and sent the placeholder
    back); they are exempt from the value checks because nothing new is
    being written for them.
    """
    secret_values = {
        value for key, value in os.environ.items() if key.startswith(SECRET_ENV_PREFIX) and value
    }
    for key, value in env.items():
        if key in preserved_keys:
            continue
        if key.startswith(SECRET_ENV_PREFIX):
            raise ConfigEditError(
                f"agent.env key '{key}' uses the secret prefix; declare it in required_secrets instead"
            )
        if REDACTION_MARKER in value:
            raise ConfigEditError(
                f"agent.env value for '{key}' contains a redaction placeholder; re-enter the full value or move it to required_secrets"
            )
        if value and value in secret_values:
            raise ConfigEditError(
                f"agent.env value for '{key}' matches a declared secret; reference it through required_secrets instead"
            )


def _merge_redacted_env(new_env: dict[str, str], existing_env: Mapping[str, Any]) -> frozenset[str]:
    """Replace redaction placeholders in ``new_env`` with the stored values.

    A form that received exactly ``[REDACTED:NAME]`` from ``config show``
    sends it back untouched; keep the stored value for that key so editing
    another field never destroys or rejects a legacy secret. Returns the keys
    that were preserved. A composite value (``prefix[REDACTED:NAME]suffix``)
    cannot be restored faithfully and is left for ``_reject_secret_env`` to
    refuse, as is a placeholder with no stored counterpart.
    """
    preserved: set[str] = set()
    for key, value in list(new_env.items()):
        if _EXACT_PLACEHOLDER_RE.fullmatch(value):
            stored = existing_env.get(key)
            if isinstance(stored, str) and stored:
                new_env[key] = stored
                preserved.add(key)
    return frozenset(preserved)


_EXACT_PLACEHOLDER_RE = re.compile(r"\[REDACTED:[A-Za-z0-9_]+\]")


def _iter_strings(value: Any) -> Iterator[str]:
    """Every string in a JSON-like value, including mapping keys."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                yield key
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def find_declared_secrets(value: Any, secrets: Mapping[str, str] | None = None) -> set[str]:
    """Names of declared secrets whose value occurs in any string of ``value``.

    Walks mapping keys and values recursively (not a serialised form, so JSON
    escaping cannot hide a match — round-14 review, 2026-09-13).
    """
    table = declared_secrets() if secrets is None else secrets
    found: set[str] = set()
    for text in _iter_strings(value):
        for name, secret in table.items():
            if secret in text:
                found.add(name)
    return found


def _reject_declared_secret_values(value: Any, what: str) -> None:
    names = find_declared_secrets(value)
    if names:
        raise ConfigEditError(
            f"{what} contains the value of declared secret(s) {', '.join(sorted(names))}; "
            "reference them via required_secrets instead of pasting the value"
        )


def _parsed_content_leaks_secret(text: str, secrets: Mapping[str, str]) -> bool:
    """True when any string (key or value) in the parsed YAML contains a
    declared secret of any length. Catches escaped forms
    (``"\\x61\\x62\\x63"``) that the text-level replacement cannot see; a
    very short secret may cause a false positive, which only blocks the raw
    view (the forms keep working). Unparseable text with backslashes is
    treated as a possible leak."""
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError:
        return "\\" in text
    for scalar in _iter_strings(parsed):
        for value in secrets.values():
            if value in scalar:
                return True
    return False


# ---------------------------------------------------------------------------
# `config show`
# ---------------------------------------------------------------------------


def _load_eval_yaml_tolerant(project_dir: Path, warnings: list[str]) -> dict[str, Any]:
    try:
        data = read_project_file(project_dir, EVAL_YAML)
    except ConfigNotFoundError:
        warnings.append("eval.yaml not found; showing an empty project")
        return {}
    except ConfigEditError as exc:
        warnings.append(f"eval.yaml ignored: {exc}")
        return {}
    try:
        return _decode_yaml_mapping(data, "eval.yaml")
    except ConfigEditError as exc:
        warnings.append(f"eval.yaml ignored: {exc}")
        return {}


def build_project_draft(project_dir: Path) -> dict[str, Any]:
    """Build the JSON payload for ``micro-eval config show``.

    Never raises for content problems (missing or unreadable eval.yaml,
    invalid configuration entries, broken or unsafe task paths); those are
    surfaced as ``warnings[]``, ``configuration_errors[]`` or
    ``tasks[].error`` so a caller always gets a usable partial view.
    """
    warnings: list[str] = []
    raw = _load_eval_yaml_tolerant(project_dir, warnings)
    secrets = declared_secrets()

    project_name = raw.get("project_name", "unnamed")
    description = raw.get("description", "")
    if not isinstance(project_name, str):
        project_name = "unnamed"
    if not isinstance(description, str):
        description = ""

    configurations: list[dict[str, Any]] = []
    configuration_errors: list[dict[str, Any]] = []
    configs_raw = raw.get("configurations")
    if configs_raw is None:
        configs_raw = []
    if isinstance(configs_raw, list):
        for index, item in enumerate(configs_raw):
            item_id = item.get("id") if isinstance(item, dict) else None
            if not isinstance(item_id, str):
                item_id = None
            try:
                spec = ConfigurationSpec.model_validate(item)
            except ValidationError as exc:
                configuration_errors.append({"index": index, "id": item_id, "error": format_validation_error(exc)})
                continue
            except (TypeError, ValueError):
                configuration_errors.append({"index": index, "id": item_id, "error": "invalid configuration entry"})
                continue
            dumped = strip_schema_version(spec.model_dump(mode="json"))
            dumped["agent"]["env"] = redact_env(dumped["agent"].get("env", {}), secrets)
            configurations.append(redact_value(dumped, secrets))
    else:
        warnings.append("configurations must be a list; ignoring")

    tasks: list[dict[str, Any]] = []
    for discovered in _discover_tasks(project_dir, raw, warnings):
        entry: dict[str, Any] = {"path": discovered.display, "task": None, "error": discovered.error}
        if discovered.rel is not None:
            try:
                task = _load_task_spec(project_dir, discovered.rel)
            except ConfigEditError as exc:
                entry["error"] = str(exc)
            else:
                entry["task"] = redact_value(strip_schema_version(task.model_dump(mode="json")), secrets)
        tasks.append(entry)

    if _is_legacy_layout(raw):
        warnings.append(
            "eval.yaml uses the legacy baseline/candidate layout; the forms cannot edit it until it is "
            "converted to configurations[] (Advanced tab)"
        )

    # Redact the whole draft once more: project fields, error ids, task
    # paths and parameter keys are strings a secret could have been pasted into.
    draft = redact_value(
        {
            "project_name": project_name,
            "description": description,
            "configurations": configurations,
            "configuration_errors": configuration_errors,
            "tasks": tasks,
            "warnings": warnings,
        },
        secrets,
    )
    # Protocol metadata is set after redaction so a declared secret that
    # happens to equal "1.0" cannot rewrite it (round-11 review).
    draft["schema_version"] = DRAFT_SCHEMA_VERSION
    return draft


# ---------------------------------------------------------------------------
# Configuration upsert / remove
# ---------------------------------------------------------------------------


def _upsert_configuration_locked(project_dir: Path, payload: dict[str, Any]) -> None:
    """Validate ``payload`` as a ConfigurationSpec and upsert it by id."""
    try:
        spec = ConfigurationSpec.model_validate(payload)
    except ValidationError as exc:
        raise ConfigEditError(format_validation_error(exc)) from exc
    if not is_safe_id(spec.id):
        raise ConfigEditError("configuration id must be a safe path segment")

    raw = load_raw_eval_yaml(project_dir)
    if not raw:
        raw = {"project_name": "unnamed", "configurations": []}

    configs = raw.get("configurations")
    if not isinstance(configs, list):
        configs = []

    existing_env: Mapping[str, Any] = {}
    for item in configs:
        if isinstance(item, dict) and item.get("id") == spec.id:
            agent = item.get("agent")
            if isinstance(agent, dict) and isinstance(agent.get("env"), dict):
                existing_env = agent["env"]
            break
    preserved = _merge_redacted_env(spec.agent.env, existing_env)
    _reject_secret_env(spec.agent.env, preserved)
    # Outside agent.env nothing is merged, so a placeholder anywhere else
    # (command, name, parameters, ...) would be persisted literally.
    outside_env = spec.model_dump(mode="json")
    outside_env["agent"].pop("env", None)
    if _contains_placeholder(outside_env):
        raise ConfigEditError("configuration contains a redaction placeholder outside agent.env; re-enter the real value")
    _reject_declared_secret_values(outside_env, "configuration")

    entry = strip_schema_version(spec.model_dump(mode="json"))
    replaced = False
    new_configs: list[Any] = []
    for item in configs:
        if isinstance(item, dict) and item.get("id") == spec.id:
            new_configs.append(entry)
            replaced = True
        else:
            new_configs.append(item)
    if not replaced:
        new_configs.append(entry)

    raw["configurations"] = new_configs
    _write_eval_yaml(project_dir, raw)


def _remove_configuration_locked(project_dir: Path, config_id: str) -> None:
    if not is_safe_id(config_id):
        raise ConfigEditError("configuration id must be a safe path segment")

    raw = load_raw_eval_yaml(project_dir)
    configs = raw.get("configurations")
    if not isinstance(configs, list):
        configs = []

    new_configs = [item for item in configs if not (isinstance(item, dict) and item.get("id") == config_id)]
    if len(new_configs) == len(configs):
        raise ConfigNotFoundError("configuration id not found")

    raw["configurations"] = new_configs
    _write_eval_yaml(project_dir, raw)


# ---------------------------------------------------------------------------
# Task upsert / remove
# ---------------------------------------------------------------------------


def _seeded_task_list(project_dir: Path, raw: dict[str, Any]) -> list[str]:
    """The task list to write: the explicit list, or the legacy glob result.

    Switching a legacy project (no ``tasks:`` or an empty list) to an explicit
    list must not silently drop the files ``micro-eval run`` was globbing.
    """
    explicit = _explicit_task_list(raw)
    if explicit is not None:
        return [str(item) for item in explicit]
    tasks_dir = _tasks_dir(raw)
    return [(tasks_dir / name).as_posix() for name in list_yaml_files(project_dir, tasks_dir)]


def _set_task_locked(project_dir: Path, payload: dict[str, Any]) -> None:
    """Validate ``payload`` as a TaskSpec, write ``<tasks_dir>/<id>.yaml``,
    and make sure eval.yaml's ``tasks:`` list references it."""
    try:
        spec = TaskSpec.model_validate(payload)
    except ValidationError as exc:
        raise ConfigEditError(format_validation_error(exc)) from exc
    if not is_safe_id(spec.id):
        raise ConfigEditError("task id must be a safe path segment")
    if not spec.input_payload.strip():
        raise ConfigEditError("input_payload must not be empty")
    if _contains_placeholder(spec.model_dump(mode="json")):
        raise ConfigEditError(
            "task contains a redaction placeholder; remove the secret from the task (secrets belong in required_secrets)"
        )
    _reject_declared_secret_values(spec.model_dump(mode="json"), "task")

    raw = load_raw_eval_yaml(project_dir)
    if not raw:
        raw = {"project_name": "unnamed"}

    # Update in place when a task with this id already exists under any
    # path (explicit list entries may live outside <tasks_dir>); otherwise
    # create <tasks_dir>/<id>.yaml.
    task_rel: PurePosixPath | None = None
    for item in _discover_tasks(project_dir, raw, []):
        if item.rel is None:
            continue
        try:
            existing = _load_task_spec(project_dir, item.rel)
        except ConfigEditError:
            continue
        if existing.id == spec.id:
            task_rel = item.rel
            break
    if task_rel is None:
        task_rel = _tasks_dir(raw) / f"{spec.id}.yaml"

    tasks_list = _seeded_task_list(project_dir, raw)
    if task_rel.as_posix() not in tasks_list:
        tasks_list.append(task_rel.as_posix())
    raw["tasks"] = tasks_list

    # Write the task file first so a later eval.yaml write failure never
    # leaves eval.yaml referencing a task file that does not exist yet.
    write_project_file(project_dir, task_rel, dump_yaml(strip_schema_version(spec.model_dump(mode="json"))))
    _write_eval_yaml(project_dir, raw)


def _remove_task_locked(project_dir: Path, *, task_id: str | None = None, path: str | None = None) -> None:
    """Delete a task file and drop it from ``tasks:``.

    Exactly one of ``task_id`` (matched against each listed task's ``id``)
    or ``path`` (a project-relative path, for entries that fail to parse)
    must be given.
    """
    if (task_id is None) == (path is None):
        raise ConfigEditError("give exactly one of task id or task path")

    raw = load_raw_eval_yaml(project_dir)
    warnings: list[str] = []
    discovered = _discover_tasks(project_dir, raw, warnings)

    target: PurePosixPath | None = None
    if path is not None:
        wanted = validate_relative_path(path)
        for item in discovered:
            if item.rel is not None and item.rel == wanted:
                target = item.rel
                break
        if target is None:
            raise ConfigNotFoundError("task path is not part of this project")
    else:
        if not is_safe_id(task_id):
            raise ConfigEditError("task id must be a safe path segment")
        for item in discovered:
            if item.rel is None:
                continue
            try:
                spec = _load_task_spec(project_dir, item.rel)
            except ConfigEditError:
                continue
            if spec.id == task_id:
                target = item.rel
                break
        if target is None:
            raise ConfigNotFoundError("task id not found")

    delete_project_file(project_dir, target)

    explicit = _explicit_task_list(raw)
    if explicit is not None:
        remaining = [str(item) for item in explicit if str(item) != target.as_posix()]
        raw["tasks"] = remaining
        _write_eval_yaml(project_dir, raw)


# ---------------------------------------------------------------------------
# Raw eval.yaml (Advanced tab) — same safety layer, comments preserved
# ---------------------------------------------------------------------------


def show_raw_config(project_dir: Path) -> dict[str, Any]:
    """Return eval.yaml text for the Advanced editor with declared secret
    values replaced by ``[REDACTED:<NAME>]``. Missing file → empty content.

    Text replacement cannot see a secret written in an escaped YAML form, so
    the redacted text is parsed again and refused outright if any string
    scalar still equals or contains a declared secret.
    """
    try:
        text = _decode_text(read_project_file(project_dir, EVAL_YAML), "eval.yaml")
    except ConfigNotFoundError:
        return {"content": "", "redacted": False}
    secrets = declared_secrets()
    content, redacted = redact_text(text, secrets)
    # Conservative final scan over the *whole* redacted text (comments and
    # all): a short secret that survived whole-word replacement, or any
    # escaped form the parser resolves to a secret, blocks the raw view.
    leaks = any(value in content for value in secrets.values()) or _parsed_content_leaks_secret(content, secrets)
    if secrets and leaks:
        raise ConfigEditError(
            "eval.yaml contains a declared secret value in a form that cannot be redacted; "
            "move it to required_secrets (the Configurations form still works)"
        )
    return {"content": content, "redacted": redacted}


def _check_existing_reference(project_dir: Path, rel: PurePosixPath) -> None:
    """If ``rel`` already exists it must be a plain file reachable without
    following any symlink; a missing path is fine (it may be created later)."""
    dirs, name = _split(rel)
    try:
        dfd = _open_dir_chain(project_dir, dirs, create=False)
    except ConfigNotFoundError:
        return
    try:
        try:
            st = os.stat(name, dir_fd=dfd, follow_symlinks=False)
        except FileNotFoundError:
            return
        _check_regular_single_link(st, "referenced task file")
    finally:
        os.close(dfd)


def _check_existing_directory(project_dir: Path, rel: PurePosixPath) -> None:
    """If ``rel`` exists it must be reachable without following any symlink."""
    try:
        os.close(_open_dir_chain(project_dir, rel.parts, create=False))
    except ConfigNotFoundError:
        return


def _validate_raw_config(project_dir: Path, content: str) -> None:
    """Apply the same rules the form-based writers enforce to hand-edited YAML.

    The text is written verbatim afterwards (comments survive), so every
    check happens here: size, encoding, mapping shape, no redaction
    placeholders, strict types for present top-level keys (a present
    ``null`` is as wrong here as it is for the loader), configuration entries
    and their env secrets, safe relative task / tasks_dir / output_dir paths,
    and no symlinked task files or task directories among the references
    that already exist.
    """
    if len(content.encode("utf-8")) > MAX_RAW_BYTES:
        raise ConfigEditError("eval.yaml too large (max 1 MiB)")
    if REDACTION_MARKER in content:
        raise ConfigEditError("content contains redaction placeholders; re-enter the real values or move them to required_secrets")
    # The whole text, comments included: a declared secret value must never
    # be persisted anywhere in eval.yaml (round-15 review, 2026-09-13).
    _reject_declared_secret_values(content, "eval.yaml")
    raw = _yaml_mapping_from_text(content, "eval.yaml")
    # And the parsed mapping: YAML escapes (\u0022, quoted folding) can spell
    # a secret that the raw text does not contain literally (round-16).
    _reject_declared_secret_values(raw, "eval.yaml")

    for key in ("project_name", "description", "output_dir"):
        if key in raw and not isinstance(raw[key], str):
            raise ConfigEditError(f"{key} must be a string")

    if "configurations" in raw:
        configs = raw["configurations"]
        if not isinstance(configs, list):
            raise ConfigEditError("configurations must be a list")
        for index, item in enumerate(configs):
            try:
                spec = ConfigurationSpec.model_validate(item)
            except ValidationError as exc:
                raise ConfigEditError(f"configurations[{index}]: {format_validation_error(exc)}") from exc
            except (TypeError, ValueError) as exc:
                raise ConfigEditError(f"configurations[{index}]: invalid entry") from exc
            if not is_safe_id(spec.id):
                raise ConfigEditError(f"configurations[{index}]: id must be a safe path segment")
            _reject_secret_env(spec.agent.env)
    else:
        # The loader still accepts the legacy baseline/candidate layout, so
        # its agent.env must pass the same secret check (round-11 review).
        for label in ("baseline", "candidate"):
            agent = raw.get(label)
            if not isinstance(agent, dict):
                continue
            env = agent.get("env") or {}
            if not isinstance(env, dict):
                raise ConfigEditError(f"{label}.env must be a mapping")
            _reject_secret_env({str(k): str(v) for k, v in env.items()})

    if "tasks" in raw:
        tasks = raw["tasks"]
        if not isinstance(tasks, list):
            raise ConfigEditError("tasks must be a list")
        for index, item in enumerate(tasks):
            try:
                rel = validate_relative_path(item)
                _check_existing_reference(project_dir, rel)
            except ConfigEditError as exc:
                raise ConfigEditError(f"tasks[{index}]: {exc}") from exc

    tasks_dir = _tasks_dir(raw)
    try:
        _check_existing_directory(project_dir, tasks_dir)
    except ConfigEditError as exc:
        raise ConfigEditError(f"tasks_dir: {exc}") from exc

    if "output_dir" in raw:
        try:
            validate_relative_path(raw["output_dir"], allow_runtime_dir=True)
        except ConfigEditError as exc:
            raise ConfigEditError(f"output_dir: {exc}") from exc


def _set_raw_config_locked(project_dir: Path, content: str) -> None:
    """Validate hand-edited eval.yaml text and write it verbatim."""
    if not isinstance(content, str):
        raise ConfigEditError("content must be a string")
    _validate_raw_config(project_dir, content)
    write_project_file(project_dir, EVAL_YAML, content)


# ---------------------------------------------------------------------------
# Public write API: every mutation takes the project lock and refuses the
# legacy layout (which the loader still reads but the forms cannot represent).
# ---------------------------------------------------------------------------


def _open_config_audit(project_dir: Path) -> int:
    """Open ``.micro-eval/config-audit.jsonl`` append-only (call under lock).

    Opened *before* the data write so a broken audit target (symlink,
    multi-link file, unwritable directory) refuses the whole operation
    instead of leaving an unaudited change behind (round-11 review). The
    file is reached through the runtime directory fd with ``O_NOFOLLOW``.
    """
    dfd = _open_dir_chain(project_dir, (RUNTIME_DIR,), create=True)
    try:
        fd = os.open(AUDIT_FILE, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=dfd)
    except OSError as exc:
        raise ConfigEditError("audit log cannot be opened", kind=INTERNAL) from exc
    finally:
        os.close(dfd)
    try:
        _check_regular_single_link(os.fstat(fd), "audit log")
    except BaseException:
        os.close(fd)
        raise
    return fd


def _append_config_audit(fd: int, member: str | None, action: str, target: str) -> None:
    """Append one ``{ts, member, action, target}`` line (ids/paths only, redacted)."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "member": member or "local",
        "action": action,
        "target": target,
    }
    data = (json.dumps(redact_value(entry, declared_secrets()), ensure_ascii=False) + "\n").encode("utf-8")
    # Write the whole line; on a short write or an error, truncate back to
    # the original length so the log never holds a torn record (round-13).
    try:
        original = os.fstat(fd).st_size
    except OSError as exc:
        raise ConfigEditError("audit log cannot be written", kind=INTERNAL) from exc
    written = 0
    try:
        while written < len(data):
            count = os.write(fd, data[written:])
            if count <= 0:
                raise OSError("short write")
            written += count
    except OSError as exc:
        try:
            os.ftruncate(fd, original)
        except OSError:
            pass
        raise ConfigEditError("audit log cannot be written", kind=INTERNAL) from exc


def _snapshot(project_dir: Path, rels: list[PurePosixPath]) -> dict[PurePosixPath, bytes | None]:
    """Current bytes of each file (``None`` when absent) for rollback."""
    snapshot: dict[PurePosixPath, bytes | None] = {}
    for rel in rels:
        try:
            snapshot[rel] = read_project_file(project_dir, rel)
        except ConfigNotFoundError:
            snapshot[rel] = None
    return snapshot


def _restore(project_dir: Path, snapshot: dict[PurePosixPath, bytes | None]) -> None:
    """Put every snapshotted file back (best effort, in reverse order)."""
    for rel, data in reversed(list(snapshot.items())):
        try:
            if data is None:
                try:
                    delete_project_file(project_dir, rel)
                except ConfigNotFoundError:
                    pass
            else:
                write_project_file(project_dir, rel, data.decode("utf-8"))
        except ConfigEditError:
            # Nothing more can be done from here; the caller reports the
            # original failure.
            continue


def _audited(
    project_dir: Path,
    member: str | None,
    action: str,
    target: str,
    touched: list[PurePosixPath],
    write: Callable[[], None],
) -> None:
    """Run ``write`` as one audited transaction over ``touched`` files.

    The audit log is opened first, the touched files are snapshotted, then
    the write runs. If the write fails part-way, or the audit line cannot
    be appended afterwards, the snapshot is restored so the project never
    carries an unaudited or half-applied change (round-11/12 reviews).
    """
    fd = _open_config_audit(project_dir)
    try:
        snapshot = _snapshot(project_dir, touched)
        try:
            write()
        except BaseException:
            _restore(project_dir, snapshot)
            raise
        try:
            _append_config_audit(fd, member, action, target)
        except BaseException:
            _restore(project_dir, snapshot)
            raise
    finally:
        os.close(fd)


def _touched_for_task(project_dir: Path, raw: dict[str, Any], *, task_id: str | None, path: str | None) -> list[PurePosixPath]:
    """Files a task write may change: eval.yaml plus the task file itself."""
    touched: list[PurePosixPath] = [EVAL_YAML]
    if path is not None:
        try:
            touched.append(validate_relative_path(path))
        except ConfigEditError:
            pass
        return touched
    if task_id is None or not is_safe_id(task_id):
        return touched
    for item in _discover_tasks(project_dir, raw, []):
        if item.rel is None:
            continue
        try:
            existing = _load_task_spec(project_dir, item.rel)
        except ConfigEditError:
            continue
        if existing.id == task_id:
            touched.append(item.rel)
            return touched
    try:
        touched.append(_tasks_dir(raw) / f"{task_id}.yaml")
    except ConfigEditError:
        pass
    return touched


def upsert_configuration(project_dir: Path, payload: dict[str, Any], *, member: str | None = None) -> None:
    with project_lock(project_dir):
        _reject_legacy_layout(load_raw_eval_yaml(project_dir))
        _audited(
            project_dir, member, "set-configuration", str(payload.get("id", "")), [EVAL_YAML],
            lambda: _upsert_configuration_locked(project_dir, payload),
        )


def remove_configuration(project_dir: Path, config_id: str, *, member: str | None = None) -> None:
    with project_lock(project_dir):
        _reject_legacy_layout(load_raw_eval_yaml(project_dir))
        _audited(
            project_dir, member, "remove-configuration", config_id, [EVAL_YAML],
            lambda: _remove_configuration_locked(project_dir, config_id),
        )


def set_task(project_dir: Path, payload: dict[str, Any], *, member: str | None = None) -> None:
    with project_lock(project_dir):
        raw = load_raw_eval_yaml(project_dir)
        _reject_legacy_layout(raw)
        task_id = payload.get("id") if isinstance(payload.get("id"), str) else None
        _audited(
            project_dir, member, "set-task", str(payload.get("id", "")),
            _touched_for_task(project_dir, raw, task_id=task_id, path=None),
            lambda: _set_task_locked(project_dir, payload),
        )


def remove_task(
    project_dir: Path,
    *,
    task_id: str | None = None,
    path: str | None = None,
    member: str | None = None,
) -> None:
    with project_lock(project_dir):
        raw = load_raw_eval_yaml(project_dir)
        _reject_legacy_layout(raw)
        _audited(
            project_dir, member, "remove-task", task_id or path or "",
            _touched_for_task(project_dir, raw, task_id=task_id, path=path),
            lambda: _remove_task_locked(project_dir, task_id=task_id, path=path),
        )


def set_raw_config(project_dir: Path, content: str, *, member: str | None = None) -> None:
    """Validate hand-edited eval.yaml text and write it verbatim (locked)."""
    with project_lock(project_dir):
        _audited(
            project_dir, member, "set-raw", "eval.yaml", [EVAL_YAML],
            lambda: _set_raw_config_locked(project_dir, content),
        )

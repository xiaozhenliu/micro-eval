"""Persistent per-cell remote sandboxes, with explicit execution/transfer boundaries.

SDKs are optional. Missing credentials, unsupported policies and transport
failures never select a local fallback. Offline SDK contracts do not establish
cloud isolation guarantees; those require credentialed integration checks.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shlex
import threading
import uuid
from pathlib import Path
from typing import Any

from micro_eval.engine.providers.base import (
    CommandResult, ExecutionRequest, IsolationLevel, NetworkPolicy, WorkspaceHandle,
)
from micro_eval.engine.providers.git_worktree import GitWorktreeProvider, WorkspaceProviderError
from micro_eval.engine.providers.remote_files import (
    CONTROL_NAMES, ENTRY_LIMIT, REMOTE_FILES, TRANSFER_CHUNK, TRANSFER_LIMIT,
    read_source, safe_relative, source_files, write_host_file,
)
from micro_eval.models.environment import WorkspaceObservation
from micro_eval.models.ids import safe_path_segment
from micro_eval.models.task import WorkspaceSpec, WorkspaceType

E2B_API_KEY_ENV = "MICRO_EVAL_SECRET_E2B_API_KEY"
MODAL_TOKEN_ID_ENV = "MICRO_EVAL_SECRET_MODAL_TOKEN_ID"
MODAL_TOKEN_SECRET_ENV = "MICRO_EVAL_SECRET_MODAL_TOKEN_SECRET"
CONTROL_TIMEOUT_S = 60.0
RECONCILE_TIMEOUT_S = 30.0

CONTROL_CREDENTIALS = frozenset({
    E2B_API_KEY_ENV, MODAL_TOKEN_ID_ENV, MODAL_TOKEN_SECRET_ENV,
    "E2B_API_KEY", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET",
})

# The SDK only receives capped frames, never a command's complete raw output.
# This is a memory bound, not an in-sandbox security boundary against the agent.
REMOTE_EXEC = r'''
import os,sys,json,base64,subprocess,selectors,threading
p=json.loads(base64.b64decode(sys.argv[1]));cap=p['cap']
env={k:v for k,v in os.environ.items() if k in {'PATH','HOME','TMPDIR','TEMP','TMP','LANG','LC_ALL'}}
env.update(p['env'])
input_cleanup_failed=threading.Event()
def clear_input():
    if p['stdin_file']:
        try:os.unlink(p['stdin_file'])
        except FileNotFoundError:pass
        except OSError:input_cleanup_failed.set()
try:
    proc=subprocess.Popen(p['argv'],cwd=p['cwd'],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
except (OSError,ValueError):
    clear_input()
    if input_cleanup_failed.is_set():os._exit(125)
    print(json.dumps({'exit_code':127,'stdout':'','stderr':'','stdout_truncated':False,'stderr_truncated':False}));sys.exit(0)
def feed():
    try:
        if p['stdin_file']:
            with open(p['stdin_file'],'rb') as source:
                while True:
                    chunk=source.read(49152)
                    if not chunk:break
                    proc.stdin.write(chunk)
    except (BrokenPipeError,OSError):pass
    finally:
        clear_input()
        try:proc.stdin.close()
        except (BrokenPipeError,OSError):pass
feeder=threading.Thread(target=feed,daemon=True);feeder.start()
s=selectors.DefaultSelector();buffers={};truncated={}
for name in ('stdout','stderr'):
    stream=getattr(proc,name);s.register(stream,selectors.EVENT_READ,name);buffers[name]=bytearray();truncated[name]=False
while s.get_map():
    for key,_ in s.select():
        data=os.read(key.fileobj.fileno(),8192)
        if not data:s.unregister(key.fileobj);key.fileobj.close();continue
        name=key.data;left=max(0,cap-len(buffers[name]));buffers[name].extend(data[:left]);truncated[name]|=len(data)>left
s.close();code=proc.wait()
clear_input()
feeder.join(timeout=1)
if feeder.is_alive() or input_cleanup_failed.is_set():os._exit(125)
print(json.dumps({'exit_code':code,**{k:base64.b64encode(v).decode() for k,v in buffers.items()},**{k+'_truncated':v for k,v in truncated.items()}}))
'''


def _payload(value: dict[str, Any]) -> str:
    return base64.b64encode(json.dumps(value).encode()).decode()


class _RemoteProvider:
    level: IsolationLevel
    root = Path("/home/user/micro-eval")

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root.resolve()
        self._control_values = {os.environ[key] for key in CONTROL_CREDENTIALS if os.environ.get(key)}
        self._sandboxes: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._cleanup_lock = threading.Lock()
        self._handles: dict[str, WorkspaceHandle] = {}

    @property
    def supported_levels(self) -> list[IsolationLevel]:
        return [self.level] if self._configured() else []

    def _configured(self) -> bool:
        raise NotImplementedError

    def _start(self, policy: NetworkPolicy) -> Any:
        raise NotImplementedError

    def _run(self, sandbox: Any, argv: list[str], *, cap: int, timeout_s: float = 60) -> str:
        raise NotImplementedError

    def _kill(self, sandbox: Any) -> str | None:
        raise NotImplementedError

    def create(self, spec: WorkspaceSpec, *, cell_id: str, run_id: str) -> WorkspaceHandle:
        if not self._configured():
            raise WorkspaceProviderError(self._credential_error())
        policy = spec.network_policy or NetworkPolicy.none
        if policy == NetworkPolicy.allowlist:
            raise WorkspaceProviderError(f"{self.name} does not implement network allowlist")
        sandbox = self._start(policy)
        handle = None
        try:
            key = uuid.uuid4().hex
            sandbox_id = self._sandbox_id(sandbox)
            if not isinstance(sandbox_id, str) or not sandbox_id:
                raise WorkspaceProviderError("remote SDK returned no sandbox identity")
            handle = WorkspaceHandle(
                workspace_path=self.root / key / "workspace", provider_name=self.name,
                isolation_level=self.level, workspace_type=spec.type, is_remote=True,
                metadata={"sandbox_id": sandbox_id, "session_key": key,
                          "network_policy_requested": (spec.network_policy.value
                                                       if spec.network_policy else "default"),
                          "network_policy_effective": policy.value, "network_policy": policy.value,
                          "trust_level": spec.trust_level.value},
            )
            with self._lock:
                self._sandboxes[key] = sandbox
                self._handles[key] = handle
            self._files(handle, {"op": "mkdir", "path": str(handle.workspace_path)})
            self._upload_sources(handle, spec, cell_id=cell_id, run_id=run_id)
            for argv in spec.setup:
                result = self.exec_command(handle, argv, timeout_s=300)
                handle.setup_exit_code = result.exit_code
                if result.exit_code != 0 or result.timed_out:
                    break
            return handle
        except BaseException:
            if handle is not None:
                self.cleanup(handle)
            else:
                try:
                    self._kill(sandbox)
                except Exception as exc:
                    raise WorkspaceProviderError("remote create failed and sandbox cleanup failed") from exc
            raise

    def _upload_sources(self, handle: WorkspaceHandle, spec: WorkspaceSpec, *,
                        cell_id: str, run_id: str) -> None:
        staging_provider = GitWorktreeProvider(self._project_root)
        staging = None
        total = count = 0
        paths: list[tuple[Path, Path]] = []
        try:
            if spec.type == WorkspaceType.git_repo:
                staging = staging_provider.create(spec.model_copy(update={"setup": []}),
                    cell_id=safe_path_segment(cell_id), run_id="remote-upload-" + uuid.uuid4().hex)
                paths = list(source_files(staging.workspace_path, self._project_root))
            elif spec.type == WorkspaceType.files:
                for item in spec.files or ([spec.path] if spec.path else []):
                    source = Path(item)
                    if not source.is_absolute():
                        source = self._project_root / source
                    if ".." in source.parts:
                        raise WorkspaceProviderError("workspace source contains parent traversal")
                    try:
                        project_relative = source.relative_to(self._project_root)
                    except ValueError as exc:
                        raise WorkspaceProviderError("workspace source escapes project root") from exc
                    if any(part in CONTROL_NAMES for part in project_relative.parts):
                        raise WorkspaceProviderError("workspace source selects a control directory")
                    entries = source_files(source, self._project_root)
                    if source.is_dir():
                        self._files(handle, {"op": "mkdir", "path": str(handle.workspace_path / source.name)})
                    for entry, relative in entries:
                        if len(paths) >= ENTRY_LIMIT:
                            raise WorkspaceProviderError("workspace exceeds remote entry limit")
                        paths.append((entry, Path(source.name) / relative if source.is_dir() else relative))
            seen: set[Path] = set()
            for entry, relative in paths:
                if relative in seen:
                    raise WorkspaceProviderError("overlapping remote workspace source paths")
                seen.add(relative)
                count += 1
                if count > ENTRY_LIMIT:
                    raise WorkspaceProviderError("workspace exceeds remote entry limit")
                if entry.is_dir():
                    self._files(handle, {"op": "mkdir", "path": str(handle.workspace_path / relative)})
                    continue
                data = read_source(entry, TRANSFER_LIMIT - total, self._project_root)
                total += len(data)
                self._write(handle, handle.workspace_path / relative, data,
                            mode=entry.stat().st_mode & 0o777)
        finally:
            if staging is not None:
                staging_provider.cleanup(staging)
                try:
                    staging.workspace_path.parent.rmdir()
                except OSError:
                    pass

    def _sandbox(self, handle: WorkspaceHandle) -> Any:
        with self._lock:
            sandbox = self._sandboxes.get(handle.metadata.get("session_key", ""))
        if sandbox is None:
            raise WorkspaceProviderError("remote sandbox is unavailable or already terminated")
        return sandbox

    def _check_path(self, handle: WorkspaceHandle, path: Path) -> None:
        roots = [handle.workspace_path]
        output = handle.metadata.get("output_path")
        if output:
            roots.append(Path(output))
        if ".." in path.parts or not path.is_absolute() or not any(path.is_relative_to(p) for p in roots):
            raise WorkspaceProviderError("remote path escapes cell filesystem")

    async def execute(self, handle: WorkspaceHandle, request: ExecutionRequest) -> CommandResult:
        try:
            return await self._execute(handle, request)
        except asyncio.CancelledError:
            # Includes cancellation while uploading stdin before process launch.
            try:
                await self._cleanup_owned(handle)
            except Exception:
                pass  # cleanup() records failure on the cell; preserve cancellation.
            raise
        except Exception:
            handle.metadata["execution_unavailable"] = "true"
            await self._cleanup_owned(handle)
            raise

    async def _execute(self, handle: WorkspaceHandle, request: ExecutionRequest) -> CommandResult:
        if not request.argv or not all(isinstance(a, str) and a for a in request.argv):
            raise ValueError("exec_command requires a non-empty argv list of non-empty strings")
        if request.output_cap_bytes < 0:
            raise ValueError("output cap must be non-negative")
        cwd = request.cwd or handle.workspace_path
        self._check_path(handle, cwd)
        env = dict(request.env or {})
        if CONTROL_CREDENTIALS.intersection(env):
            raise WorkspaceProviderError("provider control credentials cannot enter a remote command")
        control_values = self._credential_values() | self._control_values
        if any(secret in value for value in env.values() for secret in control_values if secret):
            raise WorkspaceProviderError("provider credential value cannot enter a remote command")
        stdin_path = None
        if request.stdin:
            stdin_path = handle.workspace_path / (".micro-eval-input-" + uuid.uuid4().hex)
            upload = asyncio.create_task(asyncio.to_thread(self._write, handle, stdin_path, request.stdin))
            try:
                await asyncio.shield(upload)
            except asyncio.CancelledError:
                try:
                    await self._cleanup_owned(handle)
                except (Exception, asyncio.CancelledError):
                    pass  # status records cleanup failure; preserve the cancellation.
                try:
                    await self._settle_transport(upload, handle)
                except asyncio.CancelledError:
                    pass
                raise
        data = {"argv": request.argv, "cwd": str(cwd), "env": env,
                "stdin_file": str(stdin_path) if stdin_path else None,
                "cap": request.output_cap_bytes}
        argv = ["python3", "-c", REMOTE_EXEC, _payload(data)]
        task = asyncio.create_task(asyncio.to_thread(
            self._run, self._sandbox(handle), argv,
            cap=request.output_cap_bytes * 3 + 4096,
            timeout_s=max(1, (request.timeout_s if request.timeout_s is not None else 300) + 1),
        ))
        try:
            raw = await asyncio.wait_for(asyncio.shield(task), 300 if request.timeout_s is None else request.timeout_s)
        except (TimeoutError, asyncio.CancelledError) as exc:
            cancelled = isinstance(exc, asyncio.CancelledError)
            if not cancelled:
                handle.metadata["execution_timed_out"] = "true"
            cleanup_error = None
            try:
                await self._cleanup_owned(handle)
            except asyncio.CancelledError:
                cancelled = True
            except Exception as error:
                cleanup_error = error
            try:
                await self._settle_transport(task, handle)
            except asyncio.CancelledError:
                cancelled = True
            if cancelled:
                raise asyncio.CancelledError
            if cleanup_error is not None:
                raise cleanup_error
            return CommandResult(exit_code=-1, timed_out=True)
        except Exception as exc:
            raise WorkspaceProviderError(f"{self.name} command transport failed") from exc
        try:
            result = json.loads(raw)
            stdout = base64.b64decode(result["stdout"], validate=True)
            stderr = base64.b64decode(result["stderr"], validate=True)
            if max(len(stdout), len(stderr)) > request.output_cap_bytes:
                raise ValueError("frame exceeds command cap")
            return CommandResult(
                exit_code=int(result["exit_code"]), stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
                stdout_truncated=bool(result["stdout_truncated"]),
                stderr_truncated=bool(result["stderr_truncated"]),
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise WorkspaceProviderError("invalid bounded remote command response") from exc

    async def _cleanup_owned(self, handle: WorkspaceHandle) -> None:
        cleanup = asyncio.create_task(asyncio.to_thread(self.cleanup, handle))
        interrupted = False
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                interrupted = True
        cleanup.result()
        if interrupted:
            raise asyncio.CancelledError

    async def _settle_transport(self, task: asyncio.Task, handle: WorkspaceHandle) -> None:
        deadline = asyncio.get_running_loop().time() + 5
        interrupted = False
        while not task.done():
            left = deadline - asyncio.get_running_loop().time()
            if left <= 0:
                handle.metadata["execution_transport_pending"] = "true"
                task.add_done_callback(lambda future: future.exception() if not future.cancelled() else None)
                break
            try:
                await asyncio.wait_for(asyncio.shield(task), left)
            except asyncio.CancelledError:
                interrupted = True
            except TimeoutError:
                handle.metadata["execution_transport_pending"] = "true"
                task.add_done_callback(lambda future: future.exception() if not future.cancelled() else None)
                break
            except Exception:
                break
        if task.done() and not task.cancelled():
            task.exception()
        if interrupted:
            raise asyncio.CancelledError

    def exec_command(self, handle: WorkspaceHandle, argv: list[str], *,
                     env: dict[str, str] | None = None,
                     timeout_s: float | None = None) -> CommandResult:
        return asyncio.run(self.execute(handle, ExecutionRequest(argv, env=env, timeout_s=timeout_s)))

    def _files(self, handle: WorkspaceHandle, payload: dict[str, Any]) -> Any:
        self._check_path(handle, Path(payload["path"]))
        try:
            raw = self._run(self._sandbox(handle), ["python3", "-c", REMOTE_FILES, _payload(payload)],
                            cap=1024 * 1024)
        except Exception as exc:
            handle.metadata["execution_unavailable"] = "true"
            self.cleanup(handle)
            raise WorkspaceProviderError("remote filesystem transport failed") from exc
        try:
            result = json.loads(raw)
            if result.get("ok") is not True:
                raise ValueError("remote filesystem operation rejected")
            return result["value"]
        except Exception as exc:
            raise WorkspaceProviderError("remote filesystem transfer failed") from exc

    def prepare_output(self, handle: WorkspaceHandle, host_output_dir: Path) -> Path:
        output = handle.workspace_path.parent / "output"
        handle.metadata["output_path"] = str(output)
        self._files(handle, {"op": "mkdir", "path": str(output)})
        return output

    def _write(self, handle: WorkspaceHandle, path: Path, data: bytes, *, mode: int = 0o600) -> None:
        if len(data) > TRANSFER_LIMIT:
            raise WorkspaceProviderError("remote input exceeds transfer limit")
        for offset in range(0, max(1, len(data)), TRANSFER_CHUNK):
            self._files(handle, {"op": "write", "path": str(path), "offset": offset,
                "data": base64.b64encode(data[offset:offset + TRANSFER_CHUNK]).decode(), "mode": mode})

    def write_file(self, handle: WorkspaceHandle, path: Path, data: bytes) -> None:
        self._write(handle, path, data)

    def path_exists(self, handle: WorkspaceHandle, path: Path) -> bool:
        return self._files(handle, {"op": "exists", "path": str(path)}) is True

    def collect_output(self, handle: WorkspaceHandle, execution_output: Path,
                       host_output: Path, byte_limit: int) -> bool:
        if str(execution_output) != handle.metadata.get("output_path"):
            raise WorkspaceProviderError("output transfer path does not match cell")
        if handle.metadata.get("sandbox_cleanup") == "confirmed":
            handle.metadata["output_transfer"] = "unavailable_after_termination"
            return True
        listing = self._files(handle, {"op": "list", "path": str(execution_output)})
        if not isinstance(listing, dict) or not isinstance(listing.get("entries"), list):
            raise WorkspaceProviderError("invalid remote output inventory")
        entries = listing["entries"]
        if len(entries) > ENTRY_LIMIT:
            raise WorkspaceProviderError("remote output inventory exceeds entry limit")
        remaining = min(max(0, byte_limit), TRANSFER_LIMIT)
        skipped = bool(listing.get("skipped"))
        seen: set[Path] = set()
        for entry in entries:
            try:
                relative = safe_relative(entry["path"])
                size = entry["size"]
                if (relative in seen or isinstance(size, bool) or not isinstance(size, int)
                        or size < 0 or size > remaining):
                    skipped = True
                    continue
                seen.add(relative)
                data = bytearray()
                for offset in range(0, max(1, size), TRANSFER_CHUNK):
                    raw = self._files(handle, {"op": "read", "path": str(execution_output / relative),
                        "offset": offset, "size": size, "limit": remaining})
                    chunk = base64.b64decode(raw, validate=True)
                    if len(chunk) != min(TRANSFER_CHUNK, size - offset):
                        raise ValueError("remote body changed during transfer")
                    data.extend(chunk)
                write_host_file(host_output, relative, bytes(data))
                remaining -= size
            except (WorkspaceProviderError, ValueError, TypeError, KeyError, OSError):
                skipped = True
        return skipped

    def collect_artifacts(self, handle: WorkspaceHandle) -> list:
        return []

    def collect_diff(self, handle: WorkspaceHandle) -> str | None:
        return None

    def observe_final(self, handle: WorkspaceHandle, *, byte_limit: int) -> WorkspaceObservation:
        return WorkspaceObservation(workspace_type=handle.workspace_type, warnings=("observation_unavailable",))

    def snapshot(self, handle: WorkspaceHandle) -> str:
        raise NotImplementedError("remote sandbox identity is not a reproducible snapshot")

    def restore(self, handle: WorkspaceHandle, snap: str) -> None:
        raise NotImplementedError("remote snapshot restore is not supported")

    def _abort_stream(self, sandbox: Any) -> None:
        with self._lock:
            handle = next((self._handles[key] for key, value in self._sandboxes.items()
                           if value is sandbox), None)
        if handle is not None:
            self.cleanup(handle)
        raise WorkspaceProviderError("remote control stream exceeded output cap")

    def cleanup(self, handle: WorkspaceHandle) -> None:
        with self._cleanup_lock:
            self._cleanup_locked(handle)

    def _cleanup_locked(self, handle: WorkspaceHandle) -> None:
        key = handle.metadata.get("session_key", "")
        with self._lock:
            sandbox = self._sandboxes.get(key)
        if sandbox is None:
            return
        try:
            termination = self._kill(sandbox)
        except Exception as exc:
            handle.metadata["sandbox_cleanup"] = "failed"
            raise WorkspaceProviderError(f"{self.name} sandbox termination failed") from exc
        with self._lock:
            self._sandboxes.pop(key, None)
            self._handles.pop(key, None)
        handle.metadata["sandbox_termination"] = termination or "confirmed"
        if handle.metadata.get("sandbox_cleanup") != "failed":
            handle.metadata["sandbox_cleanup"] = "confirmed"
        else:
            handle.metadata["sandbox_cleanup_retry"] = "confirmed"


class E2BProvider(_RemoteProvider):
    """One E2B VM for the cell's complete setup/agent/validation lifecycle."""
    name = "e2b"
    level = IsolationLevel.vm

    def __init__(self, project_root: Path) -> None:
        super().__init__(project_root)
        self._api_key = os.environ.get(E2B_API_KEY_ENV, "")

    def _configured(self) -> bool:
        return bool(self._api_key)

    def _credential_values(self) -> set[str]:
        return {self._api_key}

    def _credential_error(self) -> str:
        return f"E2B provider requires {E2B_API_KEY_ENV}; remote execution has no local fallback"

    def _start(self, policy: NetworkPolicy) -> Any:
        try:
            from e2b import Sandbox
        except ImportError as exc:
            raise WorkspaceProviderError("E2B SDK not installed; install micro-eval[e2b]") from exc
        try:
            return Sandbox.create(
                api_key=self._api_key, timeout=3600,
                allow_internet_access=policy == NetworkPolicy.full,
                request_timeout=CONTROL_TIMEOUT_S,
            )
        except Exception as exc:
            raise WorkspaceProviderError(
                "E2B sandbox creation failed; allocation/termination is unknown if the response was lost "
                "(the requested sandbox lifetime is 3600 seconds)"
            ) from exc

    def _sandbox_id(self, sandbox: Any) -> str:
        return sandbox.sandbox_id

    def _run(self, sandbox: Any, argv: list[str], *, cap: int, timeout_s: float = 60) -> str:
        retained = {"stdout": bytearray(), "stderr": bytearray()}

        def receive(name: str, data: str) -> None:
            encoded = data.encode()
            if len(retained[name]) + len(encoded) > cap:
                self._abort_stream(sandbox)
            retained[name].extend(encoded)

        result = sandbox.commands.run(
            shlex.join(argv), timeout=timeout_s, request_timeout=CONTROL_TIMEOUT_S,
            on_stdout=lambda data: receive("stdout", data),
            on_stderr=lambda data: receive("stderr", data),
        )
        if result.exit_code != 0:
            raise WorkspaceProviderError("remote control process failed")
        return bytes(retained["stdout"]).decode()

    def _kill(self, sandbox: Any) -> str:
        return "deleted" if sandbox.kill(request_timeout=CONTROL_TIMEOUT_S) else "already_absent"


class ModalProvider(_RemoteProvider):
    """One Modal Sandbox container per cell; no transient function invocations."""
    name = "modal"
    level = IsolationLevel.container
    root = Path("/micro-eval")

    def __init__(self, project_root: Path) -> None:
        super().__init__(project_root)
        self._token_id = os.environ.get(MODAL_TOKEN_ID_ENV, "")
        self._token_secret = os.environ.get(MODAL_TOKEN_SECRET_ENV, "")

    def _configured(self) -> bool:
        return bool(self._token_id and self._token_secret)

    def _credential_values(self) -> set[str]:
        return {self._token_id, self._token_secret}

    def _credential_error(self) -> str:
        return (f"Modal provider requires {MODAL_TOKEN_ID_ENV} and {MODAL_TOKEN_SECRET_ENV}; "
                "remote execution has no local fallback")

    def _start(self, policy: NetworkPolicy) -> Any:
        try:
            import modal
        except ImportError as exc:
            raise WorkspaceProviderError("Modal SDK not installed; install micro-eval[modal]") from exc
        async def create() -> Any:
            client = app = None
            attempted = False
            name = "micro-eval-" + uuid.uuid4().hex
            try:
                async with asyncio.timeout(CONTROL_TIMEOUT_S):
                    client = await modal.Client.from_credentials.aio(self._token_id, self._token_secret)
                    app = await modal.App.lookup.aio("micro-eval-sandbox", create_if_missing=True, client=client)
                    attempted = True
                    return await modal.Sandbox.create.aio(
                        app=app, name=name, image=modal.Image.debian_slim(python_version="3.11"),
                        timeout=3600, block_network=policy == NetworkPolicy.none, client=client,
                    )
            except Exception as creation_error:
                if attempted:
                    try:
                        async with asyncio.timeout(RECONCILE_TIMEOUT_S):
                            orphan = await modal.Sandbox.from_name.aio("micro-eval-sandbox", name, client=client)
                        async with asyncio.timeout(RECONCILE_TIMEOUT_S):
                            await orphan.terminate.aio(wait=True)
                    except Exception as cleanup_error:
                        raise WorkspaceProviderError(
                            "Modal creation failed; sandbox termination is unknown after bounded reconciliation "
                            "(the requested sandbox lifetime is 3600 seconds)"
                        ) from cleanup_error
                raise WorkspaceProviderError("Modal sandbox creation failed; any reconciled sandbox was terminated") from creation_error

        return asyncio.run(create())

    def _sandbox_id(self, sandbox: Any) -> str:
        return sandbox.object_id

    def _run(self, sandbox: Any, argv: list[str], *, cap: int, timeout_s: float = 60) -> str:
        async def run() -> str:
            async with asyncio.timeout(timeout_s + CONTROL_TIMEOUT_S):
                process = await sandbox.exec.aio(*argv, timeout=max(1, int(timeout_s)), text=False)

                async def drain(reader: Any) -> bytes:
                    retained = bytearray()
                    async for data in reader:
                        if len(retained) + len(data) > cap:
                            await asyncio.to_thread(self._abort_stream, sandbox)
                        retained.extend(data)
                    return bytes(retained)

                stdout, _ = await asyncio.gather(drain(process.stdout), drain(process.stderr))
                await process.wait.aio()
                if process.returncode != 0:
                    raise WorkspaceProviderError("remote control process failed")
                return stdout.decode()

        return asyncio.run(run())

    def _kill(self, sandbox: Any) -> str:
        async def terminate() -> None:
            async with asyncio.timeout(CONTROL_TIMEOUT_S):
                await sandbox.terminate.aio(wait=True)
        asyncio.run(terminate())
        return "terminated"

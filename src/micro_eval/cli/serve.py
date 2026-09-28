"""Server launch CLI commands."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from collections.abc import Callable, Mapping
from pathlib import Path

import typer

from micro_eval.server.models import ServerConfig, host_with_port


def _default_data_root() -> Path:
    return Path.home() / ".micro-eval-server"


LOOPBACK_HOSTS = {"", "0.0.0.0", "::", "[::]", "127.0.0.1", "localhost"}


def effective_allowed_hosts(config: ServerConfig, bind_host: str, port: int) -> list[str]:
    """Mirror the Host values accepted by the Next.js proxy at startup."""
    hosts = [host_with_port(name, port) for name in ("localhost", "127.0.0.1", "::1")]
    hosts.extend(config.allowed_hosts)
    if bind_host.strip():
        hosts.append(host_with_port(bind_host, port))
    return list(dict.fromkeys(name.strip().lower() for name in hosts if name.strip()))


def resolve_probe_host(bind_host: str) -> tuple[str, str]:
    """Map the bind host to (host to probe, host to show in the URL).

    A wildcard or loopback bind is reachable on ``127.0.0.1``, so probe that
    and show ``localhost``. Any other bind host is probed as-is and shown
    as-is, except that an IPv6 literal is bracketed for the URL
    (``--host ::1`` → ``http://[::1]:<port>/``).
    """
    if bind_host in LOOPBACK_HOSTS:
        return "127.0.0.1", "localhost"
    literal = bind_host[1:-1] if bind_host.startswith("[") and bind_host.endswith("]") else bind_host
    if ":" in literal:
        return literal, f"[{literal}]"
    return bind_host, bind_host


def next_exit_is_failure(returncode: int | None, shutdown_requested: bool) -> bool:
    """True when Next.js ended on its own with a non-zero status.

    A termination we asked for (Ctrl-C / SIGTERM handled by ``shutdown``)
    is not a failure even though the child reports a signal exit.
    """
    if shutdown_requested or returncode in (0, None):
        return False
    return True


def port_is_listening(host: str, port: int, timeout_s: float = 0.5) -> bool:
    """True if something already accepts TCP connections on host:port."""
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def open_browser_when_ready(
    url: str,
    host: str,
    port: int,
    timeout_s: float = 30.0,
    is_alive: Callable[[], bool] | None = None,
) -> None:
    """Poll until ``host:port`` accepts TCP connections, then open the browser once.

    Meant to run on a daemon thread started *after* the Next.js process was
    spawned (the caller checks beforehand that nothing else listens on the
    port, so a successful probe means our server). Stops without opening
    anything if ``is_alive`` reports the server process has exited, or if
    nothing listens within ``timeout_s``; the URL was already printed for
    the user to open by hand.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if is_alive is not None and not is_alive():
            return
        if port_is_listening(host, port):
            webbrowser.open(url)
            return
        time.sleep(0.5)


def _should_auto_open(*, no_open: bool, is_tty: bool, env: Mapping[str, str] | None = None) -> bool:
    """Decide whether serve should automatically open a browser tab."""
    source_env = env if env is not None else os.environ
    if no_open:
        return False
    if source_env.get("MICRO_EVAL_NO_OPEN") == "1":
        return False
    return is_tty


def maybe_open_browser(
    *,
    no_open: bool,
    host: str,
    port: int,
    is_tty: bool | None = None,
    env: Mapping[str, str] | None = None,
    timeout_s: float = 30.0,
    is_alive: Callable[[], bool] | None = None,
) -> threading.Thread | None:
    """Start the browser-opening daemon thread unless suppressed.

    ``host`` is the bind host; it is mapped through ``resolve_probe_host``.
    Suppressed by ``--no-open``, ``MICRO_EVAL_NO_OPEN=1``, or a
    non-interactive stdout (CI, piped output, tests). Returns the started
    (already running) thread, or ``None`` when suppressed.
    """
    resolved_is_tty = sys.stdout.isatty() if is_tty is None else is_tty
    if not _should_auto_open(no_open=no_open, is_tty=resolved_is_tty, env=env):
        return None
    probe_host, display_host = resolve_probe_host(host)
    url = f"http://{display_host}:{port}/"
    thread = threading.Thread(
        target=open_browser_when_ready, args=(url, probe_host, port, timeout_s, is_alive), daemon=True
    )
    thread.start()
    return thread


def _terminate_proc(proc: subprocess.Popen, name: str, timeout: int = 5) -> None:
    """Terminate a subprocess, escalating to kill after timeout."""
    if proc.poll() is not None:
        return
    typer.echo(f"  Stopping {name}...")
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        typer.echo(f"  Force-killing {name}...")
        proc.kill()
        proc.wait(timeout=5)


def serve_command(
    port: int = typer.Option(3000, "--port", help="HTTP port"),
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
    no_open: bool = typer.Option(
        False, "--no-open", help="Do not automatically open a browser tab once the server is ready"
    ),
) -> None:
    """Start the Team Server (Next.js + worker)."""
    data_root = data_root.expanduser()
    data_root.mkdir(mode=0o700, parents=True, exist_ok=True)

    config_path = data_root / "server.json"
    if not config_path.exists():
        config = ServerConfig(bind_host=host, bind_port=port, data_root=str(data_root))
        config_path.write_text(config.model_dump_json(indent=2))
    else:
        config = ServerConfig.model_validate_json(config_path.read_text())

    from micro_eval.server.queue import QueueDB
    db = QueueDB(data_root / "queue.db")
    db.close()

    (data_root / "workspaces").mkdir(exist_ok=True)
    (data_root / "templates").mkdir(exist_ok=True)

    # Seed bundled templates (demo-codefix, starter-tasks) so a fresh server
    # has something to run immediately. Idempotent per template id via a
    # marker file, so it never clobbers a template an admin has deliberately
    # deleted, even across restarts.
    from micro_eval.server.bundled import seed_bundled_templates
    from micro_eval.server.template import TemplateRegistry

    registry = TemplateRegistry(data_root)
    for template_id in seed_bundled_templates(data_root, registry):
        typer.echo(f"Seeded bundled template: {template_id}")

    typer.echo("Starting worker...")
    worker_proc = subprocess.Popen(
        [sys.executable, "-m", "micro_eval.cli.main", "worker", "--data-root", str(data_root)],
    )

    ui_dir = Path(__file__).resolve().parent.parent.parent.parent / "ui"
    if not ui_dir.exists():
        typer.echo(f"Error: ui/ directory not found at {ui_dir}", err=True)
        worker_proc.terminate()
        raise typer.Exit(1)

    next_dir = ui_dir / ".next"
    if not next_dir.exists():
        typer.echo("Building Next.js...")
        # Inject the same server env vars used by `next start` so build-time
        # rendering decisions (e.g. isServerMode() checks) match runtime.
        build_env = {
            **os.environ,
            "MICRO_EVAL_SERVER_MODE": "true",
            "MICRO_EVAL_DATA_ROOT": str(data_root),
        }
        build_result = subprocess.run(["npm", "run", "build"], cwd=ui_dir, env=build_env)
        if build_result.returncode != 0:
            typer.echo("Error: Next.js build failed", err=True)
            worker_proc.terminate()
            raise typer.Exit(1)
    else:
        # Warn (but don't auto-rebuild) if the existing build looks stale
        # relative to the UI sources, so startup stays predictable.
        build_id = next_dir / "BUILD_ID"
        if build_id.exists():
            build_mtime = build_id.stat().st_mtime
            ui_src = ui_dir / "src"
            if ui_src.exists():
                latest_src = max(
                    (p.stat().st_mtime for p in ui_src.rglob("*") if p.is_file()),
                    default=0,
                )
                if latest_src > build_mtime:
                    typer.echo(
                        "Warning: UI sources are newer than the last build. "
                        "Run 'cd ui && npm run build' to update.",
                        err=True,
                    )

    allowed_hosts = effective_allowed_hosts(config, host, port)
    env = {
        **os.environ,
        "MICRO_EVAL_SERVER_MODE": "true",
        "MICRO_EVAL_DATA_ROOT": str(data_root),
        # Host header allowlist (CSRF layer 4, anti DNS-rebinding). The proxy
        # also adds localhost defaults for this port. Pass the same effective
        # list that we report at startup.
        "MICRO_EVAL_BIND_PORT": str(port),
        "MICRO_EVAL_ALLOWED_HOSTS": ",".join(allowed_hosts),
    }

    typer.echo(f"Starting Next.js on {host}:{port}...")
    typer.echo(f"  Host allowlist: {', '.join(allowed_hosts)}")
    next_proc = None
    cleaned_up = False
    shutdown_requested = False

    def cleanup() -> None:
        nonlocal cleaned_up
        if cleaned_up:
            return
        cleaned_up = True
        typer.echo("\nShutting down...")
        if next_proc is not None:
            _terminate_proc(next_proc, "Next.js")
        _terminate_proc(worker_proc, "worker")

    def shutdown(signum, frame):
        nonlocal shutdown_requested
        shutdown_requested = True
        cleanup()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    probe_host, display_host = resolve_probe_host(host)
    if port_is_listening(probe_host, port):
        typer.echo(
            f"Error: something already listens on {display_host}:{port}; "
            "stop it or pick another --port.",
            err=True,
        )
        cleanup()
        raise typer.Exit(1)

    typer.echo(f"Open http://{display_host}:{port}/ in your browser")

    try:
        next_proc = subprocess.Popen(
            ["npx", "next", "start", "--port", str(port), "--hostname", host],
            cwd=ui_dir,
            env=env,
        )
        # Only now can a successful probe mean *our* server: the port was
        # free a moment ago and the probe stops if Next.js exits early.
        maybe_open_browser(
            no_open=no_open,
            host=host,
            port=port,
            is_alive=lambda: next_proc.poll() is None,
        )
        returncode: int | None = next_proc.wait()
    except KeyboardInterrupt:
        shutdown_requested = True
        returncode = None
    finally:
        cleanup()

    if next_exit_is_failure(returncode, shutdown_requested):
        typer.echo(f"Error: Next.js exited with status {returncode}", err=True)
        raise typer.Exit(1)


def worker_command(
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """Start the run worker (standalone)."""
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    data_root = data_root.expanduser()
    config_path = data_root / "server.json"
    config = None
    if config_path.exists():
        config = ServerConfig.model_validate_json(config_path.read_text())

    from micro_eval.server.worker import run_worker
    run_worker(data_root, config)

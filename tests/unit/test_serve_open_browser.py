"""Tests for the `micro-eval serve` auto-open-browser behaviour (GRO-554)."""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from micro_eval.cli.serve import (
    maybe_open_browser,
    open_browser_when_ready,
    port_is_listening,
    resolve_probe_host,
)


@pytest.mark.parametrize("bind", ["0.0.0.0", "::", "", "127.0.0.1", "localhost"])
def test_resolve_probe_host_loopback_and_wildcard(bind: str) -> None:
    assert resolve_probe_host(bind) == ("127.0.0.1", "localhost")


def test_resolve_probe_host_keeps_explicit_lan_address() -> None:
    assert resolve_probe_host("192.168.1.5") == ("192.168.1.5", "192.168.1.5")


def _listener() -> tuple[socket.socket, int]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    return sock, sock.getsockname()[1]


def _free_port() -> int:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def test_port_is_listening_reflects_socket_state() -> None:
    listener, port = _listener()
    try:
        assert port_is_listening("127.0.0.1", port) is True
    finally:
        listener.close()
    assert port_is_listening("127.0.0.1", _free_port()) is False


def test_no_open_flag_suppresses_browser() -> None:
    with patch("micro_eval.cli.serve.webbrowser.open") as mock_open:
        assert maybe_open_browser(no_open=True, host="127.0.0.1", port=1, is_tty=True, env={}) is None
        mock_open.assert_not_called()


def test_env_var_suppresses_browser() -> None:
    with patch("micro_eval.cli.serve.webbrowser.open") as mock_open:
        thread = maybe_open_browser(no_open=False, host="127.0.0.1", port=1, is_tty=True, env={"MICRO_EVAL_NO_OPEN": "1"})
        assert thread is None
        mock_open.assert_not_called()


def test_non_tty_suppresses_browser() -> None:
    with patch("micro_eval.cli.serve.webbrowser.open") as mock_open:
        assert maybe_open_browser(no_open=False, host="127.0.0.1", port=1, is_tty=False, env={}) is None
        mock_open.assert_not_called()


def test_open_browser_when_ready_opens_once_socket_listens() -> None:
    listener, port = _listener()
    try:
        with patch("micro_eval.cli.serve.webbrowser.open") as mock_open:
            open_browser_when_ready(f"http://localhost:{port}/", "127.0.0.1", port, timeout_s=2.0)
            mock_open.assert_called_once_with(f"http://localhost:{port}/")
    finally:
        listener.close()


def test_open_browser_when_ready_gives_up_quietly_when_nothing_listens() -> None:
    port = _free_port()
    with patch("micro_eval.cli.serve.webbrowser.open") as mock_open:
        open_browser_when_ready(f"http://localhost:{port}/", "127.0.0.1", port, timeout_s=1.2)
        mock_open.assert_not_called()


def test_open_browser_when_ready_stops_when_server_process_died() -> None:
    """If Next.js exits (e.g. port conflict), never open a browser on whatever
    else might start listening later."""
    port = _free_port()
    with patch("micro_eval.cli.serve.webbrowser.open") as mock_open:
        open_browser_when_ready(f"http://localhost:{port}/", "127.0.0.1", port, timeout_s=5.0, is_alive=lambda: False)
        mock_open.assert_not_called()


def test_maybe_open_browser_uses_display_host_for_lan_bind() -> None:
    listener, port = _listener()
    try:
        with patch("micro_eval.cli.serve.webbrowser.open") as mock_open:
            thread = maybe_open_browser(no_open=False, host="127.0.0.1", port=port, is_tty=True, env={}, timeout_s=2.0)
            assert thread is not None
            thread.join(timeout=3.0)
            mock_open.assert_called_once_with(f"http://localhost:{port}/")
    finally:
        listener.close()


def test_resolve_probe_host_brackets_ipv6_literal() -> None:
    from micro_eval.cli.serve import resolve_probe_host as resolve

    assert resolve("::1") == ("::1", "[::1]")
    assert resolve("[fe80::1]") == ("fe80::1", "[fe80::1]")


@pytest.mark.parametrize(
    ("returncode", "shutdown_requested", "expected"),
    [(0, False, False), (None, False, False), (1, False, True), (-15, False, True), (1, True, False), (-2, True, False)],
)
def test_next_exit_is_failure(returncode: int | None, shutdown_requested: bool, expected: bool) -> None:
    from micro_eval.cli.serve import next_exit_is_failure

    assert next_exit_is_failure(returncode, shutdown_requested) is expected

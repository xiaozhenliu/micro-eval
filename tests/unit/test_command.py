"""Tests for shared argv placeholder resolution."""

from __future__ import annotations

import sys

from micro_eval.engine.command import resolve_command_argv


def test_resolve_command_argv_injects_python_and_context_values() -> None:
    argv = resolve_command_argv(
        ["{python}", "--output={output_dir}", "{unknown}"],
        replacements={"{output_dir}": "/tmp/output"},
    )

    assert argv == [sys.executable, "--output=/tmp/output", "{unknown}"]


def test_resolve_command_argv_does_not_mutate_source_command() -> None:
    command = ["{python}", "-V"]

    resolve_command_argv(command)

    assert command == ["{python}", "-V"]

#!/usr/bin/env python3
"""Run one real local agent CLI and write a micro-eval smoke result."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

MAX_CAPTURE_CHARS = 20_000
DEFAULT_AGENT_TIMEOUT_S = 900
TEST_TIMEOUT_S = 60
CHILD_ENV_ALLOWLIST = {
    "PATH",
    "HOME",
    "TMPDIR",
    "TEMP",
    "TMP",
    "LANG",
    "LC_ALL",
    "SYSTEMROOT",
    "NO_COLOR",
}
PROMPT_ARGUMENT_FLAGS = {"--message", "--oneshot", "-z"}


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: run-agent.py <claude-code|codex-cli|openclaw|hermes> <output_file>", file=sys.stderr)
        return 2

    target = sys.argv[1]
    output_file = Path(sys.argv[2]).resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    repo_dir = Path(__file__).resolve().parents[1]
    prompt = sys.stdin.read()
    agent_output_file = output_file.with_name(f"{output_file.stem}.{target}.agent-output.txt")

    command, stdin_text = build_agent_command(target, prompt, repo_dir, agent_output_file)
    if command is None:
        write_result(
            output_file=output_file,
            target=target,
            agent_command=[target],
            agent_exit_code=127,
            agent_stdout="",
            agent_stderr=f"Unsupported target: {target}",
            agent_file_output="",
            test_exit_code=1,
            test_stdout="",
            test_stderr="Unsupported target",
        )
        return 0

    agent_result = run_command(command, cwd=repo_dir, timeout_s=agent_timeout_s(), stdin_text=stdin_text)
    test_result = run_command([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=repo_dir, timeout_s=TEST_TIMEOUT_S)
    agent_file_output = read_text(agent_output_file)

    write_result(
        output_file=output_file,
        target=target,
        agent_command=redacted_command(command, target),
        agent_exit_code=agent_result.returncode,
        agent_stdout=agent_result.stdout,
        agent_stderr=agent_result.stderr,
        agent_file_output=agent_file_output,
        test_exit_code=test_result.returncode,
        test_stdout=test_result.stdout,
        test_stderr=test_result.stderr,
    )
    return 0


def build_agent_command(
    target: str,
    prompt: str,
    repo_dir: Path,
    agent_output_file: Path,
) -> tuple[list[str] | None, str | None]:
    if target == "claude-code":
        return (
            [
                "claude",
                "-p",
                "--permission-mode",
                "acceptEdits",
                "--output-file",
                str(agent_output_file),
                "--max-turns",
                "10",
                prompt,
            ],
            None,
        )
    if target == "codex-cli":
        return (
            [
                "codex",
                "exec",
                "--skip-git-repo-check",
                "--sandbox",
                "workspace-write",
                "--ask-for-approval",
                "never",
                "-C",
                str(repo_dir),
                "-o",
                str(agent_output_file),
                "-",
            ],
            prompt,
        )
    if target == "openclaw":
        return (["openclaw", "agent", "--local", "--json", "--message", prompt, "--timeout", "600"], None)
    if target == "hermes":
        return (["hermes", "--oneshot", prompt], None)
    return (None, None)


def run_command(command: list[str], *, cwd: Path, timeout_s: int, stdin_text: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            input=stdin_text,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
            env=child_process_env(),
        )
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(command, 127, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return subprocess.CompletedProcess(command, 124, stdout, stderr or f"timed out after {timeout_s}s")


def write_result(
    *,
    output_file: Path,
    target: str,
    agent_command: list[str],
    agent_exit_code: int,
    agent_stdout: str,
    agent_stderr: str,
    agent_file_output: str,
    test_exit_code: int,
    test_stdout: str,
    test_stderr: str,
) -> None:
    status = "PASS" if test_exit_code == 0 else "FAIL"
    output_file.write_text(
        "# micro-eval agent-codefix-showdown result\n\n"
        "This is MVP smoke/use-case validation, not a benchmark-quality winner signal.\n\n"
        f"agent_target={target}\n"
        f"agent_command={agent_command}\n"
        f"agent_exit_code={agent_exit_code}\n"
        f"unit_test_exit_code={test_exit_code}\n"
        f"MICRO_EVAL_TASK_RESULT={status}\n\n"
        "## Agent final output file\n\n"
        f"{truncate(agent_file_output)}\n\n"
        "## Agent stdout\n\n"
        f"{truncate(agent_stdout)}\n\n"
        "## Agent stderr\n\n"
        f"{truncate(agent_stderr)}\n\n"
        "## Unit test stdout\n\n"
        f"{truncate(test_stdout)}\n\n"
        "## Unit test stderr\n\n"
        f"{truncate(test_stderr)}\n"
    )


def read_text(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError:
        return ""


def truncate(value: str) -> str:
    if len(value) <= MAX_CAPTURE_CHARS:
        return value
    return value[:MAX_CAPTURE_CHARS] + "\n[truncated]"


def child_process_env() -> dict[str, str]:
    """Build the narrow environment passed to nested local agent CLIs."""
    env = {key: value for key, value in os.environ.items() if key in CHILD_ENV_ALLOWLIST}
    env.setdefault("NO_COLOR", "1")
    return env


def redacted_command(command: list[str], target: str) -> list[str]:
    redacted: list[str] = []
    skip_next = False
    for index, part in enumerate(command):
        if skip_next:
            redacted.append("[prompt-or-path]")
            skip_next = False
            continue
        if target == "claude-code" and index == len(command) - 1:
            redacted.append("[prompt-or-path]")
            continue
        redacted.append(part)
        if part in PROMPT_ARGUMENT_FLAGS:
            skip_next = True
    if len(redacted) > 12:
        return redacted[:12] + ["..."]
    return redacted


def agent_timeout_s() -> int:
    raw = os.environ.get("MICRO_EVAL_AGENT_TIMEOUT_S", "")
    if raw.isdigit():
        return int(raw)
    return DEFAULT_AGENT_TIMEOUT_S


if __name__ == "__main__":
    raise SystemExit(main())
